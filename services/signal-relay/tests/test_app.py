from fastapi.testclient import TestClient

from signal_relay.app import create_app
from signal_relay.bridge import RelayBridge
from signal_relay.config import Settings


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
        )
    )
    bridge.start()
    assert bridge.health()["transport"] == "reticulum"
    assert bridge.contact()["address"]
    assert bridge._delivery_destination.hash
    bridge.stop()