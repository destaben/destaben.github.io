from fastapi.testclient import TestClient
import ipaddress
import json
import logging
import pytest
import RNS
from urllib.error import HTTPError
from urllib.parse import urlsplit

from signal_relay import home_assistant
from signal_relay.app import create_app
from signal_relay.bridge import LAB_SESSION_FIELD, LabSession, RelayBridge
from signal_relay.config import MESHTASTIC_ENTITY_KEYS, Settings, _public_tcp_node_urls
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
                "channels": [{"name": "Longfast", "last": {"nodeId": "!7e5d1a**", "text": "Hello mesh", "time": "2026-09-25T08:14:00Z", "hops": 2}}],
                "refreshedAt": "2026-09-25T08:15:00Z",
            }

    app.state.meshtastic_status = Meshtastic()
    with TestClient(app) as client:
        response = client.get("/v1/lab/meshtastic-status")
        assert response.status_code == 200
        assert response.json() == {
            "status": "available",
            "onlineNodes": 12,
            "totalNodes": 43,
            "channels": [{"name": "Longfast", "last": {"nodeId": "!7e5d1a**", "text": "Hello mesh", "time": "2026-09-25T08:14:00Z", "hops": 2}}],
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

_MESHTASTIC_ENTITY_IDS = {
    **{key: f"sensor.private_{key}" for key in MESHTASTIC_ENTITY_KEYS},
    "gateway": "meshtastic.gateway_private",
    "nodes_online": "sensor.private_online",
    "nodes_total": "sensor.private_total",
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
    assert app.state.meshtastic_status is None
    with TestClient(app) as client:
        response = client.get("/v1/lab/meshtastic-status")
        assert response.status_code == 503
        assert response.json()["detail"] == "meshtastic_status_unavailable"


@pytest.mark.parametrize("online_state", [None, "44", "-1"])
def test_meshtastic_status_returns_503_for_null_or_inconsistent_counts(tmp_path, monkeypatch, online_state):
    monkeypatch.setattr(home_assistant, "urlopen", _fake_home_assistant_api({
        "/api/": {"message": "API running."},
        "/api/states/meshtastic.gateway_private": {"state": "Connected"},
        "/api/states/sensor.private_online": {"state": online_state},
        "/api/states/sensor.private_total": {"state": "43"},
    }))
    app = create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
            **_HOME_ASSISTANT_SETTINGS, meshtastic_entity_ids=_MESHTASTIC_ENTITY_IDS,
        )
    )
    with TestClient(app) as client:
        response = client.get("/v1/lab/meshtastic-status")
        assert response.status_code == 503
        assert response.json()["detail"] == "meshtastic_status_unavailable"


_MESHTASTIC_CHANNEL_FIELDS = {
    "text": "message",
    "node_id": "from_id",
    "hop_start": "hop_start",
    "hop_limit": "hop_limit",
}


def _meshtastic_channel_responses(states=None):
    return {
        "/api/": {"message": "API running."},
        "/api/states/meshtastic.gateway_private": {"state": "Connected"},
        "/api/states/sensor.private_online": {"state": "12"},
        "/api/states/sensor.private_total": {"state": "43"},
        "/api/states": [] if states is None else states,
    }


def _meshtastic_channel_app(tmp_path, channel_allowlist=frozenset({"Longfast"})):
    return create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
            **_HOME_ASSISTANT_SETTINGS, meshtastic_entity_ids=_MESHTASTIC_ENTITY_IDS,
            meshtastic_channel_fields=_MESHTASTIC_CHANNEL_FIELDS,
            meshtastic_channel_allowlist=frozenset(channel_allowlist),
        )
    )


def test_meshtastic_route_omits_channels_when_no_channel_is_allowlisted(tmp_path, monkeypatch):
    states = [{
        "entity_id": "meshtastic.gateway_private_channel_longfast", "state": "Hello mesh",
        "last_changed": "2026-09-25T08:14:00+00:00", "attributes": {"message": "Hello mesh", "from_id": "!7e5d1a42"},
    }]
    monkeypatch.setattr(home_assistant, "urlopen", _fake_home_assistant_api(_meshtastic_channel_responses(states)))

    with TestClient(_meshtastic_channel_app(tmp_path, channel_allowlist=frozenset())) as client:
        response = client.get("/v1/lab/meshtastic-status")

    assert response.status_code == 200
    assert "channels" not in response.json()
    assert "Hello mesh" not in response.text


def test_meshtastic_route_does_not_publish_a_person_named_channel_that_is_not_allowlisted(tmp_path, monkeypatch):
    states = [{
        "entity_id": "meshtastic.gateway_private_channel_alice_phone", "state": "SENTINEL-ALICE-TEXT",
        "last_changed": "2026-09-25T08:14:00+00:00", "attributes": {"message": "SENTINEL-ALICE-TEXT", "from_id": "!7e5d1a42", "friendly_name": "Alice"},
    }]
    monkeypatch.setattr(home_assistant, "urlopen", _fake_home_assistant_api(_meshtastic_channel_responses(states)))

    with TestClient(_meshtastic_channel_app(tmp_path)) as client:
        response = client.get("/v1/lab/meshtastic-status")

    assert response.status_code == 200
    assert response.json()["channels"] == []
    assert "SENTINEL" not in response.text
    assert "Alice" not in response.text


def test_meshtastic_route_publishes_only_the_whitelisted_channel_projection(tmp_path, monkeypatch):
    states = [
        {
            "entity_id": "meshtastic.gateway_private_channel_longfast", "state": "Hello mesh",
            "last_changed": "2026-09-25T08:14:00+00:00",
            "attributes": {
                "message": "Hello mesh", "from_id": "!7e5d1a42", "hop_start": 3, "hop_limit": 1,
                "long_name": "SENTINEL-AUTHOR", "serial": "SENTINEL-SERIAL", "mac_address": "SENTINEL-MAC",
                "friendly_name": "Longfast", "previous_message": "SENTINEL-OLDER",
            },
        },
        {
            "entity_id": "meshtastic.gateway_private_channel_direct_messages", "state": "SENTINEL-DM",
            "last_changed": "2026-09-25T08:14:00+00:00", "attributes": {"message": "SENTINEL-DM", "from_id": "!7e5d1a42"},
        },
        {
            "entity_id": "sensor.unrelated_channel_other", "state": "SENTINEL-OTHER",
            "last_changed": "2026-09-25T08:14:00+00:00", "attributes": {"message": "SENTINEL-OTHER", "from_id": "!7e5d1a42"},
        },
    ]
    monkeypatch.setattr(home_assistant, "urlopen", _fake_home_assistant_api(_meshtastic_channel_responses(states)))

    with TestClient(_meshtastic_channel_app(tmp_path)) as client:
        response = client.get("/v1/lab/meshtastic-status")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"status", "onlineNodes", "totalNodes", "channels", "refreshedAt"}
    assert payload["channels"] == [{
        "name": "Longfast",
        "last": {"nodeId": "!7e5d1a**", "text": "Hello mesh", "time": "2026-09-25T08:14:00Z", "hops": 2},
    }]
    for channel in payload["channels"]:
        assert set(channel) <= {"name", "last"}
        assert set(channel["last"]) <= {"nodeId", "text", "time", "hops"}
    for sentinel in ("SENTINEL", "!7e5d1a42", "Direct", "direct_messages", "meshtastic.", "sensor.", "gateway_private", "unrelated"):
        assert sentinel not in response.text, sentinel


def test_meshtastic_route_omits_channels_when_discovery_fails_instead_of_returning_503(tmp_path, monkeypatch):
    responses = _meshtastic_channel_responses()

    def urlopen(request, timeout):
        path = urlsplit(request.full_url).path
        if path == "/api/states":
            raise HTTPError(request.full_url, 500, "Failure", None, None)
        return _JSONResponse(responses[path])

    monkeypatch.setattr(home_assistant, "urlopen", urlopen)
    with TestClient(_meshtastic_channel_app(tmp_path)) as client:
        response = client.get("/v1/lab/meshtastic-status")

    assert response.status_code == 200
    assert set(response.json()) == {"status", "onlineNodes", "totalNodes", "refreshedAt"}
    assert response.json()["onlineNodes"] == 12


def test_meshtastic_route_still_returns_503_when_the_gateway_is_disconnected(tmp_path, monkeypatch):
    responses = _meshtastic_channel_responses([{
        "entity_id": "meshtastic.gateway_private_channel_longfast", "state": "Hello", "last_changed": "2026-09-25T08:14:00+00:00",
        "attributes": {"message": "Hello", "from_id": "!7e5d1a42"},
    }])
    responses["/api/states/meshtastic.gateway_private"] = {"state": "disconnected"}
    monkeypatch.setattr(home_assistant, "urlopen", _fake_home_assistant_api(responses))

    with TestClient(_meshtastic_channel_app(tmp_path)) as client:
        response = client.get("/v1/lab/meshtastic-status")

    assert response.status_code == 503
    assert response.json()["detail"] == "meshtastic_status_unavailable"


@pytest.mark.parametrize("entity_setting", [
    "SIGNAL_RELAY_HOME_ASSISTANT_TEMPERATURE_ENTITY_ID",
    "SIGNAL_RELAY_HOME_ASSISTANT_HUMIDITY_ENTITY_ID",
    "SIGNAL_RELAY_HOME_ASSISTANT_AIR_QUALITY_ENTITY_ID",
])
@pytest.mark.parametrize("bad_value", [
    "Sensor.Private", "sensor.private/../../api", "sensor", "sensor.private?x=1", " sensor.private",
    "zha2/living.temp", "zha-2.living_temp", "zha2.living room", "zha2..temp", "zha2.Living_temp", "ZHA2.living_temp",
])
def test_entity_ids_are_validated_and_bad_values_are_not_echoed(monkeypatch, entity_setting, bad_value):
    monkeypatch.setenv(entity_setting, bad_value)

    with pytest.raises(ValueError) as error:
        Settings.from_environment()

    assert str(error.value) == f"{entity_setting} must be a Home Assistant entity ID"
    assert bad_value not in str(error.value)


@pytest.mark.parametrize("entity_id", ["zha2.living_room_temp", "2nd_floor.temperature", "sensor.2nd_floor", "123.456"])
def test_home_assistant_domains_may_start_with_digits_as_home_assistant_allows(monkeypatch, entity_id):
    monkeypatch.setenv("SIGNAL_RELAY_HOME_ASSISTANT_TEMPERATURE_ENTITY_ID", entity_id)

    assert Settings.from_environment().home_assistant_temperature_entity_id == entity_id


def test_valid_entity_ids_are_accepted_and_empty_entity_ids_are_unset(monkeypatch):
    entity_ids = {**{key: f"sensor.private_{key}" for key in MESHTASTIC_ENTITY_KEYS}, "nodes_total": "sensor.private_total_2"}
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS", json.dumps(entity_ids))
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX", "")

    settings = Settings.from_environment()

    assert settings.meshtastic_entity_ids["nodes_total"] == "sensor.private_total_2"
    assert settings.meshtastic_channel_prefix is None
    assert settings.meshtastic_channel_denylist == frozenset()
    assert settings.meshtastic_channel_fields is None


def test_channel_prefix_denylist_and_fields_are_parsed_from_the_environment(monkeypatch):
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX", "meshtastic.gateway_private_channel_")
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST", " Telemetry, Secret Room ,,")
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS", '{"text": "message", "node_id": "from_id", "timestamp": "rx_time", "hop_start": "hop_start", "hop_limit": "hop_limit"}')

    settings = Settings.from_environment()

    assert settings.meshtastic_channel_prefix == "meshtastic.gateway_private_channel_"
    assert settings.meshtastic_channel_denylist == frozenset({"Telemetry", "Secret Room"})
    assert settings.meshtastic_channel_fields == {
        "text": "message", "node_id": "from_id", "timestamp": "rx_time", "hop_start": "hop_start", "hop_limit": "hop_limit",
    }


@pytest.mark.parametrize("bad_value", ["Sensor.Private", "sensor", "sensor.private/../x", " sensor.meshtastic_channel_", "sensor.a?x=1"])
def test_channel_prefix_must_be_an_entity_id_shaped_prefix(monkeypatch, bad_value):
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX", bad_value)

    with pytest.raises(ValueError) as error:
        Settings.from_environment()

    assert str(error.value) == "SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX must be a Home Assistant entity ID prefix"
    assert bad_value not in str(error.value)


@pytest.mark.parametrize("bad_name", ["bad/name", "x" * 33, "<script>", "name?x=1", "Ünïcode name"])
def test_channel_denylist_entries_are_validated_without_echoing_them(monkeypatch, bad_name):
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST", f"Telemetry,{bad_name}")

    with pytest.raises(ValueError) as error:
        Settings.from_environment()

    assert str(error.value) == "SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST must contain channel names of 1 to 32 letters, digits, spaces, underscores, or hyphens"
    assert bad_name not in str(error.value)


def test_channel_allowlist_is_parsed_from_the_environment_and_empty_means_no_channels(monkeypatch):
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST", " Longfast, Field Team ,,")

    assert Settings.from_environment().meshtastic_channel_allowlist == frozenset({"Longfast", "Field Team"})

    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST", "")

    assert Settings.from_environment().meshtastic_channel_allowlist == frozenset()


@pytest.mark.parametrize("bad_name", ["bad/name", "x" * 33, "<script>", "name?x=1", "Ünïcode name"])
def test_channel_allowlist_entries_are_validated_without_echoing_them(monkeypatch, bad_name):
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST", f"Longfast,{bad_name}")

    with pytest.raises(ValueError) as error:
        Settings.from_environment()

    assert str(error.value) == "SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST must contain channel names of 1 to 32 letters, digits, spaces, underscores, or hyphens"
    assert bad_name not in str(error.value)


@pytest.mark.parametrize("configured, effective", [("60", 900), ("0", 900), ("899", 900), ("900", 900), ("1200", 1200)])
def test_status_cache_seconds_has_a_900_second_floor(monkeypatch, configured, effective):
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_STATUS_CACHE_SECONDS", configured)

    assert Settings.from_environment().meshtastic_status_cache_seconds == effective


@pytest.mark.parametrize("bad_value", [
    "not json",
    "null",
    '["message"]',
    '{"author": "from_name"}',
    '{"text": "bad/attr"}',
    '{"text": 3}',
    '{"text": null}',
    '{"text": ""}',
    '{"text": "' + "x" * 65 + '"}',
])
def test_channel_fields_must_map_supported_fields_to_attribute_names_without_echoing_them(monkeypatch, bad_value):
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS", bad_value)

    with pytest.raises(ValueError) as error:
        Settings.from_environment()

    assert str(error.value) == "SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS must be a JSON object that maps supported fields to attribute names"
    assert "from_name" not in str(error.value)
    assert "bad/attr" not in str(error.value)


@pytest.mark.parametrize("bad_value", ["Sensor.Private", "sensor.private/../../api", "sensor", "sensor.private?x=1", " sensor.private"])
def test_meshtastic_entity_map_rejects_bad_entity_ids_without_echoing_them(monkeypatch, bad_value):
    entity_ids = {**{key: f"sensor.private_{key}" for key in MESHTASTIC_ENTITY_KEYS}, "gateway": bad_value}
    monkeypatch.setenv("SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS", json.dumps(entity_ids))

    with pytest.raises(ValueError) as error:
        Settings.from_environment()

    assert str(error.value) == "SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS contains an invalid entity ID"
    assert bad_value not in str(error.value)


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


@pytest.mark.parametrize("embedded_form", [
    "tcp://[2002:0a00:0001::]:4403",
    "tcp://[2002:0808:0808::]:4242",
    "tcp://[64:ff9b:1::a00:1]:4242",
    "tcp://[64:ff9b:1:0:0:0:0:1]:4242",
    "tcp://[2001:0:4136:e378::1]:4242",
    "tcp://[2001::1]:4242",
])
def test_public_tcp_node_urls_reject_ipv4_embedding_ipv6_forms_even_if_the_stdlib_reports_them_global(monkeypatch, embedded_form):
    # Simulates a runtime whose ipaddress module classifies these forms as global: the explicit prefix rules must still reject them.
    monkeypatch.setattr(ipaddress.IPv6Address, "is_global", property(lambda self: True))

    with pytest.raises(ValueError, match="must not contain private IP addresses"):
        _public_tcp_node_urls(json.dumps({"Node One": embedded_form}))


def test_public_tcp_node_urls_keep_native_global_ipv6_literals_valid():
    assert _public_tcp_node_urls('{"Node One": "tcp://[2606:4700:4700::1111]:4242"}') == {"Node One": "tcp://[2606:4700:4700::1111]:4242"}


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


def test_meshtastic_endpoints_require_private_configuration(tmp_path):
    app = create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
        )
    )
    with TestClient(app) as client:
        assert client.get("/v1/lab/meshtastic").status_code == 503
        assert client.post("/v1/lab/meshtastic/messages", json={"message": "Hello", "turnstileToken": "token"}).status_code == 503


def test_meshtastic_message_requires_turnstile_and_respects_cooldown(tmp_path, monkeypatch):
    entity_ids = {key: f"sensor.{key}" for key in MESHTASTIC_ENTITY_KEYS}
    app = create_app(
        Settings(
            mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2,
            rate_window_seconds=60, reticulum_config_dir=None, storage_dir=tmp_path,
            telegram_bot_token=None, telegram_chat_id=None,
            home_assistant_url="http://nginx:8081", home_assistant_token="private-token",
            meshtastic_entity_ids=entity_ids, meshtastic_turnstile_secret="private-secret",
        )
    )

    class Meshtastic:
        def __init__(self):
            self.messages = []

        def broadcast(self, message):
            self.messages.append(message)

    meshtastic = Meshtastic()
    app.state.meshtastic = meshtastic
    monkeypatch.setattr("signal_relay.app.verify_turnstile", lambda *_: True)
    with TestClient(app) as client:
        assert client.post("/v1/lab/meshtastic/messages", json={"message": " Hello", "turnstileToken": "token"}).status_code == 422
        accepted = client.post(
            "/v1/lab/meshtastic/messages",
            json={"message": "Hello mesh", "turnstileToken": "token"},
            headers={"X-Real-IP": "203.0.113.10"},
        )
        assert accepted.status_code == 202
        assert accepted.json() == {"status": "accepted"}
        assert meshtastic.messages == ["Hello mesh"]
        assert client.post(
            "/v1/lab/meshtastic/messages",
            json={"message": "Again", "turnstileToken": "token"},
            headers={"X-Real-IP": "203.0.113.10"},
        ).status_code == 429
