from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge

from .config import Settings
from .telegram import TelegramNotifier

LAB_SESSION_FIELD = "signal_relay_session"
logger = logging.getLogger("uvicorn.error")


@dataclass
class LabSession:
    expires_at: float
    source_hash: str
    destination_hash: str
    state: str = "identity_ready"
    error_code: str | None = None
    sent_count: int = 0
    delivery_observed: bool = False
    node_alias: str = ""


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
        self._lab_sessions: dict[str, LabSession] = {}
        self._lab_session_lock = threading.Lock()
        self._tcp_node_statuses: dict[str, str] = {}
        self._tcp_node_lock = threading.Lock()
        self._tcp_node_monitor_stop = threading.Event()
        self._tcp_node_monitor: threading.Thread | None = None
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
        self._refresh_tcp_node_statuses()
        if self.settings.public_tcp_node_aliases:
            self._tcp_node_monitor = threading.Thread(target=self._monitor_tcp_nodes, daemon=True)
            self._tcp_node_monitor.start()

    def stop(self) -> None:
        self._tcp_node_monitor_stop.set()
        if self._tcp_node_monitor:
            self._tcp_node_monitor.join(timeout=1)
        self._clients.clear()
        self._lab_sessions.clear()

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

    def lab_capabilities(self) -> dict[str, bool]:
        return {
            "educationalSending": (
                self.settings.lab_send_enabled
                and self.settings.lab_sender_config_dir is not None
                and self.transport == "reticulum"
            ),
            "telegramNotifications": self._telegram is not None,
        }

    def reticulum_nodes(self) -> dict[str, object]:
        aliases = self.settings.public_tcp_node_aliases or {}
        urls = self.settings.public_tcp_node_urls or {}
        if self.transport != "reticulum" or not aliases or set(urls) != set(aliases.values()):
            return {"status": "unavailable", "nodes": []}
        with self._tcp_node_lock:
            nodes = [
                {"alias": alias, "url": urls[alias], "status": self._tcp_node_statuses.get(alias, "down")}
                for alias in aliases.values()
            ]
        return {"status": "available", "nodes": nodes}

    def _monitor_tcp_nodes(self) -> None:
        while not self._tcp_node_monitor_stop.wait(20):
            self._refresh_tcp_node_statuses()

    def _refresh_tcp_node_statuses(self) -> None:
        aliases = self.settings.public_tcp_node_aliases or {}
        if not aliases:
            return
        try:
            import RNS

            connected_names = {
                str(interface.name)
                for interface in RNS.Transport.interfaces
                if type(interface).__name__ == "TCPClientInterface" and getattr(interface, "online", False)
            }
        except Exception:
            for alias in aliases.values():
                logger.warning("Reticulum TCP node connection check failed: node=%s", alias)
            connected_names = set()

        with self._tcp_node_lock:
            for interface_name, alias in aliases.items():
                status = "up" if interface_name in connected_names else "down"
                previous = self._tcp_node_statuses.get(alias)
                self._tcp_node_statuses[alias] = status
                if previous != status:
                    logger.info("Reticulum TCP node connection changed: node=%s status=%s", alias, status)

    def inbox_notices(self) -> list[dict[str, str]]:
        return self.inbox

    def create_lab_session(self) -> dict[str, str]:
        if not self.settings.lab_send_enabled:
            raise PermissionError("lab_disabled")
        if self.transport != "reticulum" or self._delivery_destination is None:
            raise RuntimeError("transport_unavailable")

        session_id = secrets.token_urlsafe(24)
        expires_at = time.monotonic() + 15 * 60
        session = LabSession(
            expires_at=expires_at,
            source_hash="",
            destination_hash=self.contact()["address"] or "",
        )
        with self._lab_session_lock:
            self._clean_lab_sessions()
            self._lab_sessions[session_id] = session
        return self._lab_session_status(session_id, session)

    def lab_session_status(self, session_id: str) -> dict[str, str]:
        with self._lab_session_lock:
            self._clean_lab_sessions()
            session = self._lab_sessions.get(session_id)
            if session is None:
                raise KeyError("session_not_found")
            return self._lab_session_status(session_id, session)

    def send_lab_message(self, session_id: str, content: str) -> dict[str, str]:
        if not self.settings.lab_send_enabled:
            raise PermissionError("lab_disabled")
        if self.transport != "reticulum" or self._router is None or self._delivery_destination is None:
            raise RuntimeError("transport_unavailable")

        with self._lab_session_lock:
            self._clean_lab_sessions()
            session = self._lab_sessions.get(session_id)
            if session is None:
                raise KeyError("session_not_found")
            if session.sent_count >= 1:
                raise ValueError("session_message_limit")
            session.sent_count += 1
            session.state = "queued"

        if self.settings.lab_sender_config_dir is None:
            self._set_lab_session_state(session_id, "failed", "lab_sender_unconfigured")
            raise RuntimeError("lab_sender_unconfigured")

        threading.Thread(
            target=self._send_lab_message_from_isolated_runtime,
            args=(session_id, content),
            daemon=True,
        ).start()
        return self.lab_session_status(session_id)

    def _send_lab_message_from_isolated_runtime(self, session_id: str, content: str) -> None:
        config_dir = self.settings.lab_sender_config_dir
        if config_dir is None:
            return
        source_root = Path(__file__).resolve().parent.parent
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(source_root) + os.pathsep + environment.get("PYTHONPATH", "")
        try:
            process = subprocess.run(
                [sys.executable, "-m", "signal_relay.lab_sender", str(config_dir)],
                input=json.dumps(
                    {
                        "destinationHash": self.public_address,
                        "content": content,
                        "sessionId": session_id,
                        "nodeAliases": self.settings.public_tcp_node_aliases or {},
                    }
                ),
                text=True,
                capture_output=True,
                timeout=70,
                check=False,
                env=environment,
            )
            result = json.loads(process.stdout)
            self._complete_lab_session(session_id, result)
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            self._set_lab_session_state(session_id, "failed", "delivery_timeout")

    def _set_lab_session_state(self, session_id: str, state: str, error_code: str | None = None) -> None:
        with self._lab_session_lock:
            session = self._lab_sessions.get(session_id)
            if session and session.expires_at > time.monotonic():
                if session.delivery_observed and state == "failed":
                    return
                session.state = state
                session.error_code = error_code

    def _complete_lab_session(self, session_id: str, result: dict[str, str]) -> None:
        source_hash = result.get("sourceHash", "")
        node_alias = result.get("nodeAlias", "")
        allowed_aliases = set((self.settings.public_tcp_node_aliases or {}).values())
        with self._lab_session_lock:
            session = self._lab_sessions.get(session_id)
            if session is None or session.expires_at <= time.monotonic():
                return
            if source_hash:
                session.source_hash = source_hash
            if node_alias in allowed_aliases:
                session.node_alias = node_alias
            delivered_to_inbox = bool(source_hash) and any(
                notice.get("sourceHash") == source_hash for notice in self.inbox
            )
            if session.delivery_observed or session.state == "delivered" or delivered_to_inbox:
                session.state = "delivered"
                session.error_code = None
                logger.info("Reticulum lab delivery completed: node=%s", session.node_alias or "unconfirmed")
                return
            session.state = result.get("state", "failed")
            session.error_code = result.get("errorCode") or None
            logger.info(
                "Reticulum lab delivery finished: node=%s state=%s",
                session.node_alias or "unconfirmed",
                session.state,
            )

    def _mark_lab_delivery_observed(self, source_hash: str, session_id: str = "") -> bool:
        if not source_hash and not session_id:
            return False
        delivery_observed = False
        with self._lab_session_lock:
            sessions = (
                [self._lab_sessions[session_id]]
                if session_id in self._lab_sessions
                else self._lab_sessions.values()
            )
            for session in sessions:
                if session.expires_at > time.monotonic() and (session_id or session.source_hash == source_hash):
                    if source_hash:
                        session.source_hash = source_hash
                    session.delivery_observed = True
                    session.state = "delivered"
                    session.error_code = None
                    delivery_observed = True
        return delivery_observed

    def _clean_lab_sessions(self) -> None:
        now = time.monotonic()
        for session_id, session in list(self._lab_sessions.items()):
            if session.expires_at <= now:
                del self._lab_sessions[session_id]

    @staticmethod
    def _lab_session_status(session_id: str, session: LabSession) -> dict[str, str]:
        return {
            "sessionId": session_id,
            "state": session.state,
            "errorCode": session.error_code or "",
            "nodeAlias": session.node_alias,
            "expiresInSeconds": str(max(0, int(session.expires_at - time.monotonic()))),
        }

    def _on_lxmf_delivery(self, message: Any) -> None:
        source_hash = getattr(message, "source_hash", b"")
        fields = getattr(message, "fields", {})
        session_id = self._lab_session_marker(fields)
        observed = self.record_incoming_message(
            message.content_as_string() or "",
            source_hash.hex() if isinstance(source_hash, bytes) else "",
            session_id,
        )
        logger.info("LXMF delivery received: correlated=%s", observed)

    @staticmethod
    def _lab_session_marker(fields: Any) -> str:
        if not isinstance(fields, dict):
            return ""
        marker = fields.get(LAB_SESSION_FIELD, fields.get(LAB_SESSION_FIELD.encode(), b""))
        if isinstance(marker, bytes):
            try:
                return marker.decode("utf-8")
            except UnicodeDecodeError:
                return ""
        return marker if isinstance(marker, str) else ""

    def record_incoming_message(self, content: str, source_hash: str = "", session_id: str = "") -> bool:
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
        observed = self._mark_lab_delivery_observed(source_hash, session_id)
        self._notify_telegram(notice["content"], source_hash)
        return observed

    def _notify_telegram(self, content: str, source_hash: str = "") -> None:
        if not self._telegram:
            return

        def notify() -> None:
            try:
                self._telegram.send_message(content, source_hash)
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