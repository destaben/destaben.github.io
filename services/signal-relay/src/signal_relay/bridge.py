from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
import json
from pathlib import Path
import secrets
import threading
import time
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge

from .config import Settings
from .telegram import TelegramNotifier


class RelayBridge:
    """Publishes a deliberately small, anonymous public event surface."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.started_at = datetime.now(UTC)
        self.message_count = 0
        self.last_acknowledgement_ms: int | None = None
        self._clients: set[Any] = set()
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self._reticulum: Any | None = None
        self._router: Any | None = None
        self._delivery_destination: Any | None = None
        self.public_address: str | None = None
        self.inbox: list[dict[str, str]] = []
        self.transport = "demo"
        self.state = "ready"
        self.metrics = CollectorRegistry()
        self.inbound_messages = Counter(
            "signal_relay_lxmf_messages_received_total",
            "LXMF messages received by Signal Relay.",
            registry=self.metrics,
        )
        self.inbox_size = Gauge(
            "signal_relay_inbox_messages",
            "Sanitized inbound message notices retained by Signal Relay.",
            registry=self.metrics,
        )
        self.telegram_notifications = Counter(
            "signal_relay_telegram_notifications_total",
            "Telegram notifications attempted by Signal Relay.",
            ["result"],
            registry=self.metrics,
        )
        self._telegram = (
            TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
            if settings.telegram_bot_token and settings.telegram_chat_id
            else None
        )

    def start(self) -> None:
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        self._load_inbox()
        if self.settings.mode == "demo":
            return
        if self.settings.mode != "reticulum":
            raise ValueError("SIGNAL_RELAY_MODE must be 'demo' or 'reticulum'")

        import LXMF
        import RNS

        self._reticulum = RNS.Reticulum(
            configdir=str(self.settings.reticulum_config_dir) if self.settings.reticulum_config_dir else None,
        )
        identity_path = self.settings.storage_dir / "lxmf-identity"
        identity = RNS.Identity.from_file(str(identity_path)) if identity_path.exists() else RNS.Identity()
        if not identity_path.exists():
            identity.to_file(str(identity_path))
        self._router = LXMF.LXMRouter(identity=identity, storagepath=str(self.settings.storage_dir / "lxmf"))
        self._delivery_destination = self._router.register_delivery_identity(identity, display_name="David Estaben")
        self._router.register_delivery_callback(self._on_lxmf_delivery)
        self._delivery_destination.announce()
        self.public_address = RNS.hexrep(self._delivery_destination.hash, delimit=False)
        self.transport = "reticulum"

    def stop(self) -> None:
        self._clients.clear()

    def health(self) -> dict[str, str]:
        return {
            "status": self.state,
            "lastHeartbeat": self.started_at.isoformat().replace("+00:00", "Z"),
            "transport": self.transport,
        }

    def status(self) -> dict[str, str | int | None]:
        return {
            "relay": "signal-relay",
            "state": self.state,
            "transport": self.transport,
            "messageCount": self.message_count,
            "lastAcknowledgementMs": self.last_acknowledgement_ms,
            "inboxCount": len(self.inbox),
            "address": self.public_address,
        }

    def contact(self) -> dict[str, str | None]:
        return {"scheme": "lxmf.delivery", "address": self.public_address}

    def inbox_notices(self) -> list[dict[str, str]]:
        return self.inbox

    def _on_lxmf_delivery(self, message: Any) -> None:
        self.record_incoming_message(message.content_as_string() or "")

    def record_incoming_message(self, content: str) -> None:
        notice = {
            "id": secrets.token_urlsafe(8),
            "receivedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "content": " ".join(content.split())[:1000],
        }
        self.inbox.insert(0, notice)
        del self.inbox[20:]
        self.inbound_messages.inc()
        self.inbox_size.set(len(self.inbox))
        self._save_inbox()
        self._notify_telegram(notice["content"])

    def _notify_telegram(self, content: str) -> None:
        if not self._telegram:
            return

        def notify() -> None:
            try:
                self._telegram.send_message(content)
                self.telegram_notifications.labels(result="sent").inc()
            except Exception:
                self.telegram_notifications.labels(result="failed").inc()

        threading.Thread(target=notify, daemon=True).start()

    @property
    def _inbox_path(self) -> Path:
        return self.settings.storage_dir / "inbox.json"

    def _load_inbox(self) -> None:
        if self._inbox_path.exists():
            self.inbox = json.loads(self._inbox_path.read_text(encoding="utf-8"))[:20]
        self.inbox_size.set(len(self.inbox))

    def _save_inbox(self) -> None:
        self._inbox_path.write_text(json.dumps(self.inbox), encoding="utf-8")

    def accept_request(self, client_id: str) -> bool:
        now = time.monotonic()
        requests = self._requests[client_id]
        while requests and now - requests[0] >= self.settings.rate_window_seconds:
            requests.popleft()
        if len(requests) >= self.settings.rate_limit:
            return False
        requests.append(now)
        return True

    async def connect(self, websocket: Any) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        await websocket.send_json({"type": "relay.status", "data": self.status()})

    def disconnect(self, websocket: Any) -> None:
        self._clients.discard(websocket)

    async def publish(self, event_type: str, data: dict[str, str | int | None]) -> None:
        stale_clients: list[Any] = []
        for client in self._clients:
            try:
                await client.send_json({"type": event_type, "data": data})
            except RuntimeError:
                stale_clients.append(client)
        for client in stale_clients:
            self.disconnect(client)

    async def send_signal(self, client_id: str, action: str) -> tuple[int, dict[str, str | int]]:
        event_id = secrets.token_urlsafe(12)
        if not self.accept_request(client_id):
            payload = {"id": event_id, "code": "rate_limited"}
            await self.publish("signal.rejected", payload)
            return 429, payload

        accepted = {"id": event_id, "action": action}
        await self.publish("signal.accepted", accepted)
        if self.transport != "demo":
            rejected = {"id": event_id, "code": "transport_not_configured"}
            await self.publish("signal.rejected", rejected)
            return 503, rejected

        self.message_count += 1
        self.last_acknowledgement_ms = 0
        acknowledgement = {"id": event_id, "acknowledgementMs": self.last_acknowledgement_ms}
        await self.publish("signal.acknowledged", acknowledgement)
        return 202, acknowledgement