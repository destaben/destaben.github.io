from fastapi.testclient import TestClient
import json
import logging
import pytest
import RNS
from urllib.parse import urlsplit

from signal_relay import home_assistant
from signal_relay.app import create_app
from signal_relay.bridge import LAB_SESSION_FIELD, LabSession, RelayBridge
from signal_relay.config import Settings, _public_tcp_node_urls
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


def test_meshtastic_status_only_returns_aggregate_public_signals(tmp_path):
    app = create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
        )
    )

    class Meshtastic:
        def status(self):
            return {
                "status": "available",
                "onlineNodes": 12,
                "totalNodes": 43,
                "lastNode": "Field relay",
                "refreshedAt": "2026-09-25T08:15:00Z",
            }

    app.state.meshtastic = Meshtastic()
    with TestClient(app) as client:
        response = client.get("/v1/lab/meshtastic-status")
        assert response.status_code == 200
        assert response.json() == {
            "status": "available",
            "onlineNodes": 12,
            "totalNodes": 43,
            "lastNode": "Field relay",
            "refreshedAt": "2026-09-25T08:15:00Z",
        }
        assert "entity_id" not in response.text
        assert "attributes" not in response.text


class _JSONResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self, *args):
        return self._body


def _fake_home_assistant_api(responses):
    def urlopen(request, timeout):
        return _JSONResponse(responses[urlsplit(request.full_url).path])

    return urlopen


_HOME_ASSISTANT_SETTINGS = {
    "home_assistant_url": "http://home-assistant:8123",
    "home_assistant_token": "private-token",
    "home_assistant_temperature_entity_id": "sensor.private_temperature",
    "home_assistant_humidity_entity_id": "sensor.private_humidity",
    "home_assistant_air_quality_entity_id": "sensor.private_air_quality",
}

_MESHTASTIC_SETTINGS = {
    "meshtastic_gateway_entity_id": "meshtastic.gateway_private",
    "meshtastic_nodes_online_entity_id": "sensor.private_online",
    "meshtastic_nodes_total_entity_id": "sensor.private_total",
}


def test_home_status_returns_503_when_a_home_assistant_state_is_null(tmp_path, monkeypatch):
    app = create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None, **_HOME_ASSISTANT_SETTINGS,
        )
    )
    monkeypatch.setattr(home_assistant, "urlopen", _fake_home_assistant_api({
        "/api/": {"message": "API running."},
        "/api/states/sensor.private_temperature": {"state": None, "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"}},
        "/api/states/sensor.private_humidity": {"state": "42", "attributes": {"device_class": "humidity", "unit_of_measurement": "%"}},
        "/api/states/sensor.private_air_quality": {"state": "8", "attributes": {"device_class": "pm25", "unit_of_measurement": "µg/m³"}},
    }))
    with TestClient(app) as client:
        response = client.get("/v1/lab/home-status")
        assert response.status_code == 503
        assert response.json()["detail"] == "home_status_unavailable"


def test_meshtastic_status_is_unavailable_without_private_configuration(tmp_path):
    app = create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
        )
    )
    assert app.state.meshtastic is None
    with TestClient(app) as client:
        response = client.get("/v1/lab/meshtastic-status")
        assert response.status_code == 503
        assert response.json()["detail"] == "meshtastic_status_unavailable"


@pytest.mark.parametrize("online_state", [None, "44", "-1"])
def test_meshtastic_status_returns_503_for_null_or_inconsistent_counts(tmp_path, monkeypatch, online_state):
    monkeypatch.setattr(home_assistant, "urlopen", _fake_home_assistant_api({
        "/api/": {"message": "API running."},
        "/api/states/meshtastic.gateway_private": {"state": "connected"},
        "/api/states/sensor.private_online": {"state": online_state},
        "/api/states/sensor.private_total": {"state": "43"},
    }))
    app = create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
            **_HOME_ASSISTANT_SETTINGS, **_MESHTASTIC_SETTINGS,
        )
    )
    with TestClient(app) as client:
        response = client.get("/v1/lab/meshtastic-status")
        assert response.status_code == 503
        assert response.json()["detail"] == "meshtastic_status_unavailable"


@pytest.mark.parametrize("entity_setting", [
    "SIGNAL_RELAY_MESHTASTIC_GATEWAY_ENTITY_ID",
    "SIGNAL_RELAY_MESHTASTIC_NODES_ONLINE_ENTITY_ID",
    "SIGNAL_RELAY_MESHTASTIC_NODES_TOTAL_ENTITY_ID",
    "SIGNAL_RELAY_MESHTASTIC_LAST_NODE_ENTITY_ID",
    "SIGNAL_RELAY_HOME_ASSISTANT_TEMPERATURE_ENTITY_ID",
    "SIGNAL_RELAY_HOME_ASSISTANT_HUMIDITY_ENTITY_ID",
    "SIGNAL_RELAY_HOME_ASSISTANT_AIR_QUALITY_ENTITY_ID",
])
@pytest.mark.parametrize("bad_value", ["Sensor.Private", "sensor.private/../../api", "sensor", "sensor.private?x=1", " sensor.private"])
def test_entity_ids_are_validated_and_bad_values_are_not_echoed(monkeypatch, entity_setting, bad_value):
    monkeypatch.setenv(entity_setting, bad_value)

    with pytest.raises(ValueError) as error:
        Settings.from_environment()

    assert str(error.value) == f"{entity_setting} must be a Home Assistant entity ID"
    assert bad_value not in str(error.value)


def test_valid_entity_ids_are_accepted_and_empty_entity_ids_are_unset(monkeypatch):
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_NODES_TOTAL_ENTITY_ID", "sensor.private_total_2")
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_LAST_NODE_ENTITY_ID", "")

    settings = Settings.from_environment()

    assert settings.meshtastic_nodes_total_entity_id == "sensor.private_total_2"
    assert settings.meshtastic_last_node_entity_id is None


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
            public_tcp_node_urls={"Node One": "tcp://node-one.example:4242"},
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
    assert bridge.reticulum_nodes() == {
        "status": "available",
        "nodes": [{"alias": "Node One", "url": "tcp://node-one.example:4242", "status": "up"}],
    }
    assert "node=Node One status=up" in caplog.text

    TCPClientInterface.online = False
    bridge._refresh_tcp_node_statuses()
    assert bridge.reticulum_nodes()["nodes"][0]["status"] == "down"
    assert "node=Node One status=down" in caplog.text
    assert "internal-tcp" not in caplog.text


def test_public_tcp_node_urls_require_safe_complete_tcp_endpoints(monkeypatch):
    monkeypatch.setenv("SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES", '{"private-interface": "Node One"}')
    monkeypatch.setenv("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS", '{"Node One": "tcp://node-one.example:4242"}')
    settings = Settings.from_environment()
    assert settings.public_tcp_node_urls == {"Node One": "tcp://node-one.example:4242"}

    for value in (
        '{"Node One": "tcp://node-one.example:4242"}',
        '{"Node One": "tcp://node.example.org:4242"}',
        '{"Node One": "tcp://1.1.1.1:4242"}',
        '{"Node One": "tcp://[2001:4860:4860::8888]:4242"}',
    ):
        assert _public_tcp_node_urls(value) == {"Node One": json.loads(value)["Node One"]}

    for value in (
        '{"Node One": "https://node-one.example:4242"}',
        '{"Node One": "tcp://127.0.0.1:4242"}',
        '{"Node One": "tcp://node-one.example"}',
        '{"Node One": "tcp://node-one.example:4242/path"}',
        '{"Node One": "tcp://localhost:4242"}',
        '{"Node One": "tcp://nas:4242"}',
        '{"Node One": "tcp://nas.lan:4242"}',
        '{"Node One": "tcp://nas.local:4242"}',
        '{"Node One": "tcp://hub.internal:4242"}',
        '{"Node One": "tcp://hub.home.arpa:4242"}',
        '{"Node One": "tcp://hub.localdomain:4242"}',
        '{"Node One": "tcp://0x7f.1:4242"}',
        '{"Node One": "tcp://127.1:4242"}',
        '{"Node One": "tcp://0177.0.0.1:4242"}',
        '{"Node One": "tcp://127.0.0.1.:4242"}',
        '{"Node One": "tcp://192.168.1.10.:4242"}',
        '{"Node One": "tcp://[64:ff9b::7f00:1]:4242"}',
        '{"Node One": "tcp://[::127.0.0.1]:4242"}',
        '{"Node One": "tcp://[::7f00:1]:4242"}',
        '{"Node One": "tcp://[::8.8.8.8]:4242"}',
        '{"Node One": "tcp://[1.1.1.1]:4242"}',
        '{"Node One": "tcp://2001:4860:4860::8888:4242"}',
        '{"Node One": "tcp://[2001:4860:4860::8888%25eth0]:4242"}',
        '{"Node One": "tcp://nas.\uff2c\uff21\uff2e:4242"}',
        '{"Node One": "tcp://x.nas\u3002lan:4242"}',
        '{"Node One": "tcp://node\u00adone.example:4242"}',
        '{"Node One": "tcp://node\u200bone.example:4242"}',
        '{"Node One": "tcp://node\u200cone.example:4242"}',
        '{"Node One": "tcp://node\u200done.example:4242"}',
        '{"Node One": "tcp://node\u2060one.example:4242"}',
        '{"Node One": "tcp://\ufeffnode-one.example:4242"}',
        '{"Node One": "tcp://node-one.example:4242?"}',
        '{"Node One": "tcp://node-one.example:4242?token=1"}',
        '{"Node One": "tcp://node-one.example:4242#"}',
        '{"Node One": "tcp://node-one.example:4242#fragment"}',
        '{"Node One": "tcp://node-one.example:4242 "}',
        '{"Node One": "tcp://node-one.example:4242\\t"}',
        '{"Node One": "tcp://node-one.example:4242x"}',
        '{"Node One": "tcp://node-one.example:+4242"}',
        '{"Node One": "tcp://node-one.example%2e:4242"}',
        '{"Node One": "tcp://node%2done.example:4242"}',
        '{"Node One": "tcp://node..example:4242"}',
        '{"Node One": "tcp://node-one.example.:4242"}',
    ):
        try:
            _public_tcp_node_urls(value)
        except ValueError:
            continue
        raise AssertionError(f"expected invalid public TCP URL: {value}")

    monkeypatch.setenv("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS", '{"Other Node": "tcp://node-one.example:4242"}')
    try:
        Settings.from_environment()
    except ValueError as error:
        assert "one URL for every public alias" in str(error)
    else:
        raise AssertionError("expected URL aliases to match public aliases")


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
    assert set(session) == {"sessionId", "state", "errorCode", "nodeAlias", "expiresInSeconds"}
    assert session["state"] == "identity_ready"
    assert session["errorCode"] == ""
    assert "sourceHash" not in session
    assert "destinationHash" not in session
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
    assert "sourceHash" not in bridge.lab_session_status("session")
    assert bridge._lab_sessions["session"].source_hash == source_hash
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
