from contextlib import asynccontextmanager
import asyncio
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .bridge import RelayBridge
from .config import Settings
from .home_assistant import HomeAssistantLabClient
from .metrics import PrometheusLabClient


class SignalRequest(BaseModel):
    action: Literal["ping"]


class DemoInboxMessage(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class LabMessage(BaseModel):
    content: str = Field(min_length=1, max_length=280)


def create_app(settings: Settings | None = None) -> FastAPI:
    relay_settings = settings or Settings.from_environment()
    bridge = RelayBridge(relay_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        bridge.start()
        yield
        bridge.stop()

    app = FastAPI(title="Reticulum Contact", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(relay_settings.allowed_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.bridge = bridge
    app.state.prometheus = PrometheusLabClient(relay_settings.prometheus_url) if relay_settings.prometheus_url else None
    home_assistant_settings = (
        relay_settings.home_assistant_url,
        relay_settings.home_assistant_token,
        relay_settings.home_assistant_temperature_entity_id,
        relay_settings.home_assistant_humidity_entity_id,
        relay_settings.home_assistant_air_quality_entity_id,
    )
    app.state.home_assistant = (
        HomeAssistantLabClient(
            relay_settings.home_assistant_url or "",
            relay_settings.home_assistant_token or "",
            relay_settings.home_assistant_temperature_entity_id or "",
            relay_settings.home_assistant_humidity_entity_id or "",
            relay_settings.home_assistant_air_quality_entity_id or "",
            relay_settings.home_assistant_cache_seconds,
        )
        if all(home_assistant_settings)
        else None
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return bridge.health()

    @app.get("/v1/status")
    async def relay_status() -> dict[str, str | int | None]:
        return bridge.status()

    @app.get("/v1/contact")
    async def contact() -> dict[str, str | None]:
        return bridge.contact()

    @app.get("/v1/inbox")
    async def inbox() -> dict[str, list[dict[str, str]]]:
        return {"messages": bridge.inbox_notices()}

    @app.get("/v1/lab/capabilities", include_in_schema=False)
    async def lab_capabilities() -> dict[str, bool]:
        return bridge.lab_capabilities()

    @app.get("/v1/lab/reticulum-nodes", include_in_schema=False)
    async def reticulum_nodes() -> dict[str, object]:
        return bridge.reticulum_nodes()

    @app.get("/v1/lab/metrics", include_in_schema=False)
    async def lab_metrics(metric: Literal["cpu", "memory"], start: int, end: int, step: int = 120) -> dict[str, object]:
        prometheus = app.state.prometheus
        now = int(time.time())
        if prometheus is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="metrics_unavailable")
        if start >= end or end > now + 300 or end - start > 604800 or step < 30 or step > 900:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_time_range")
        try:
            return await asyncio.to_thread(prometheus.query_range, metric, start, end, step)
        except (OSError, RuntimeError, ValueError):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="metrics_unavailable") from None

    @app.get("/v1/lab/home-status", include_in_schema=False)
    async def home_status() -> dict[str, object]:
        home_assistant = app.state.home_assistant
        if home_assistant is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="home_status_unavailable")
        try:
            return await asyncio.to_thread(home_assistant.status)
        except (OSError, RuntimeError, ValueError):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="home_status_unavailable") from None

    @app.post("/v1/lab/sessions", status_code=status.HTTP_201_CREATED, include_in_schema=False)
    async def create_lab_session(request: Request) -> dict[str, str]:
        try:
            return bridge.create_lab_session()
        except PermissionError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error

    @app.get("/v1/lab/sessions/{session_id}", include_in_schema=False)
    async def lab_session(session_id: str) -> dict[str, str]:
        try:
            return bridge.lab_session_status(session_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session_not_found") from error

    @app.post("/v1/lab/sessions/{session_id}/messages", include_in_schema=False)
    async def send_lab_message(session_id: str, payload: LabMessage, request: Request) -> dict[str, str]:
        try:
            return bridge.send_lab_message(session_id, payload.content)
        except PermissionError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session_not_found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)) from error

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(bridge.metrics), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/demo/inbox", status_code=status.HTTP_201_CREATED, include_in_schema=False)
    async def demo_inbox(payload: DemoInboxMessage) -> dict[str, list[dict[str, str]]]:
        if relay_settings.mode != "demo":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        bridge.record_incoming_message(payload.content)
        return {"messages": bridge.inbox_notices()}

    @app.post("/v1/signals", status_code=status.HTTP_202_ACCEPTED)
    async def signal(payload: SignalRequest, request: Request) -> dict[str, str | int]:
        client_id = request.client.host if request.client else "unknown"
        result_status, response = await bridge.send_signal(client_id, payload.action)
        if result_status != status.HTTP_202_ACCEPTED:
            raise HTTPException(status_code=result_status, detail=response["code"])
        return response

    @app.websocket("/v1/events")
    async def events(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        if origin not in relay_settings.allowed_origins:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await bridge.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            bridge.disconnect(websocket)

    return app


app = create_app()