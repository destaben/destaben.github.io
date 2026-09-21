from fastapi.testclient import TestClient
import logging
import RNS

from signal_relay.app import create_app
from signal_relay.bridge import LAB_SESSION_FIELD, LabSession, RelayBridge
from signal_relay.config import Settings
from signal_relay.lab_sender import public_node_alias


def test_metrics_endpoint_only_returns_fixed_container_series(tmp_path):
    app = create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None, prometheus_url="http://prometheus:9090",
        )
    )

    class Prometheus:
        def query_range(self, metric, start, end, step):
            assert metric == "cpu"
            assert end > start
            assert step == 120
            return {"metric": metric, "start": start, "end": end, "series": [{"name": "cadvisor", "values": [[start, 0.2]]}]}

    app.state.prometheus = Prometheus()
    with TestClient(app) as client:
        response = client.get("/v1/lab/metrics", params={"metric": "cpu", "start": 1, "end": 2, "step": 120})
        assert response.status_code == 200
        assert response.json()["series"][0]["name"] == "cadvisor"
        assert client.get("/v1/lab/metrics", params={"metric": "cpu", "start": 2, "end": 1}).status_code == 422


def test_home_status_only_returns_rounded_public_signals(tmp_path):
    app = create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
        )
    )

    class HomeAssistant:
        def status(self):
            return {
                "status": "available",
                "temperatureC": 22,
                "humidityPercent": 45,
                "airQuality": "good",
                "refreshedAt": "2026-09-19T08:15:00Z",
            }

    app.state.home_assistant = HomeAssistant()
    with TestClient(app) as client:
        response = client.get("/v1/lab/home-status")
        assert response.status_code == 200
        assert response.json() == {
            "status": "available",
            "temperatureC": 22,
            "humidityPercent": 45,
            "airQuality": "good",
            "refreshedAt": "2026-09-19T08:15:00Z",
        }
        assert client.get("/v1/lab/home-status").json().get("entity_id") is None


def test_home_status_is_unavailable_without_private_configuration(tmp_path):
    app = create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
        )
    )
    with TestClient(app) as client:
        assert client.get("/v1/lab/home-status").status_code == 503


def test_health_status_and_signal_acknowledgement(tmp_path):
    app = create_app(
        Settings(
            mode="demo",
            allowed_origins={"http://127.0.0.1:4321"},
            rate_limit=2,
            rate_window_seconds=60,
            reticulum_config_dir=None,
            storage_dir=tmp_path,
            telegram_bot_token=None,
            telegram_chat_id=None,
        )
    )
    with TestClient(app) as client:
        assert client.get("/healthz").json()["transport"] == "demo"
        assert client.get("/v1/contact").json()["address"] is None
        assert client.get("/v1/lab/reticulum-nodes").json() == {"status": "unavailable", "nodes": []}
        assert client.get("/v1/lab/capabilities").json() == {
            "educationalSending": False,
            "telegramNotifications": False,
        }
        with client.websocket_connect("/v1/events", headers={"origin": "http://127.0.0.1:4321"}) as socket:
            assert socket.receive_json()["type"] == "relay.status"
            response = client.post("/v1/signals", json={"action": "ping"})
            assert response.status_code == 202
            assert socket.receive_json()["type"] == "signal.accepted"
            assert socket.receive_json()["type"] == "signal.acknowledged"
        assert client.get("/v1/status").json()["messageCount"] == 1
        bridge = app.state.bridge
        bridge.record_incoming_message("A real message body")
        inbox = client.get("/v1/inbox").json()["messages"]
        assert len(inbox) == 1
        assert set(inbox[0]) == {"id", "receivedAt", "content"}
        assert inbox[0]["content"] == "A real message body"
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "signal_relay_lxmf_messages_received_total" in metrics.text
        demo_message = client.post("/v1/demo/inbox", json={"content": "Hello from curl"})
        assert demo_message.status_code == 201
        assert demo_message.json()["messages"][0]["content"] == "Hello from curl"


def test_tcp_node_projection_uses_only_configured_aliases_and_logs_transitions(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    bridge = RelayBridge(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=1,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
            public_tcp_node_aliases={"internal-tcp": "Node One"},
        )
    )

    class TCPClientInterface:
        name = "internal-tcp"
        online = True

    class PrivateInterface:
        name = "private-tcp"
        online = True

    monkeypatch.setattr(RNS.Transport, "interfaces", [TCPClientInterface(), PrivateInterface()])
    bridge.transport = "reticulum"
    bridge._refresh_tcp_node_statuses()
    assert bridge.reticulum_nodes() == {"status": "available", "nodes": [{"alias": "Node One", "status": "up"}]}
    assert "node=Node One status=up" in caplog.text

    TCPClientInterface.online = False
    bridge._refresh_tcp_node_statuses()
    assert bridge.reticulum_nodes()["nodes"][0]["status"] == "down"
    assert "node=Node One status=down" in caplog.text
    assert "internal-tcp" not in caplog.text


def test_rejects_invalid_and_rate_limited_signals(tmp_path):
    app = create_app(
        Settings(
            mode="demo",
            allowed_origins={"http://127.0.0.1:4321"},
            rate_limit=1,
            rate_window_seconds=60,
            reticulum_config_dir=None,
            storage_dir=tmp_path,
            telegram_bot_token=None,
            telegram_chat_id=None,
        )
    )
    with TestClient(app) as client:
        assert client.post("/v1/signals", json={"action": "message"}).status_code == 422
        assert client.post("/v1/signals", json={"action": "ping"}).status_code == 202
        assert client.post("/v1/signals", json={"action": "ping"}).status_code == 429


def test_lab_session_endpoints_are_disabled_by_default(tmp_path):
    app = create_app(
        Settings(
            mode="demo",
            allowed_origins={"http://127.0.0.1:4321"},
            rate_limit=2,
            rate_window_seconds=60,
            reticulum_config_dir=None,
            storage_dir=tmp_path,
            telegram_bot_token=None,
            telegram_chat_id=None,
        )
    )
    with TestClient(app) as client:
        response = client.post("/v1/lab/sessions")
        assert response.status_code == 503
        assert response.json()["detail"] == "lab_disabled"


def test_initialises_the_official_reticulum_runtime(tmp_path):
    bridge = RelayBridge(
        Settings(
            mode="reticulum",
            allowed_origins={"http://127.0.0.1:4321"},
            rate_limit=1,
            rate_window_seconds=60,
            reticulum_config_dir=tmp_path / "reticulum",
            storage_dir=tmp_path / "data",
            telegram_bot_token=None,
            telegram_chat_id=None,
            lab_send_enabled=True,
        )
    )
    bridge.start()
    assert bridge.health()["transport"] == "reticulum"
    assert bridge.contact()["address"]
    assert bridge._delivery_destination.hash
    assert bridge.lab_capabilities()["educationalSending"] is False
    session = bridge.create_lab_session()
    assert session["state"] == "identity_ready"
    assert session["errorCode"] == ""
    assert session["sourceHash"] != session["destinationHash"]
    assert bridge.inbox_notices() == []
    assert "identity" not in session
    bridge.stop()


def test_received_source_hash_confirms_matching_lab_session(tmp_path):
    bridge = RelayBridge(
        Settings(
            mode="demo",
            allowed_origins={"http://127.0.0.1:4321"},
            rate_limit=1,
            rate_window_seconds=60,
            reticulum_config_dir=None,
            storage_dir=tmp_path,
            telegram_bot_token=None,
            telegram_chat_id=None,
        )
    )
    source_hash = "a3fa0fe454aea978747d86c7142c6210"
    bridge._lab_sessions["session"] = LabSession(
        expires_at=9999999999,
        source_hash="",
        destination_hash="destination",
        state="queued",
    )

    class IncomingMessage:
        def __init__(self, incoming_source_hash: str):
            self.source_hash = bytes.fromhex(incoming_source_hash)
            self.fields = {LAB_SESSION_FIELD.encode(): b"session"}

        @staticmethod
        def content_as_string():
            return "Hello from Reticulum"

    bridge._on_lxmf_delivery(IncomingMessage(source_hash))
    bridge._complete_lab_session(
        "session",
        {"sourceHash": source_hash, "state": "failed", "errorCode": "delivery_timeout"},
    )
    bridge._set_lab_session_state("session", "failed", "delivery_timeout")

    assert "sourceHash" not in bridge.inbox_notices()[0]
    assert bridge.lab_session_status("session")["sourceHash"] == source_hash
    assert bridge.lab_session_status("session")["state"] == "delivered"


def test_lab_session_only_returns_configured_node_alias(tmp_path):
    bridge = RelayBridge(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=1,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
            public_tcp_node_aliases={"internal-tcp": "Node One"},
        )
    )
    bridge._lab_sessions["session"] = LabSession(
        expires_at=9999999999, source_hash="", destination_hash="destination", state="queued"
    )

    bridge._complete_lab_session("session", {"state": "failed", "errorCode": "delivery_failed", "nodeAlias": "private-tcp"})
    assert bridge.lab_session_status("session")["nodeAlias"] == ""

    bridge._complete_lab_session("session", {"state": "failed", "errorCode": "delivery_failed", "nodeAlias": "Node One"})
    assert bridge.lab_session_status("session")["nodeAlias"] == "Node One"


def test_isolated_sender_only_translates_the_selected_configured_route_interface():
    route_interface = type("RouteInterface", (), {"name": "internal-tcp"})()
    aliases = {"internal-tcp": "Node One"}

    assert public_node_alias(route_interface, aliases) == "Node One"
    assert public_node_alias(None, aliases) == ""
    assert public_node_alias(type("RouteInterface", (), {"name": "private-tcp"})(), aliases) == ""
    assert public_node_alias(route_interface, ["Node One"]) == ""