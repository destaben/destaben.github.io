import pytest

from signal_relay.home_assistant import (
    MESHTASTIC_BROADCAST_TIMEOUT_SECONDS,
    HomeAssistantLabClient,
    HomeAssistantMeshtasticClient,
)


def test_meshtastic_broadcast_uses_the_extended_fixed_service_timeout(monkeypatch):
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("signal_relay.home_assistant.urlopen", fake_urlopen)
    client = HomeAssistantMeshtasticClient("http://home-assistant", "private-token", {})

    client.broadcast("Hello mesh")

    assert captured == {
        "url": "http://home-assistant/api/services/script/meshtastic_public_broadcast",
        "timeout": MESHTASTIC_BROADCAST_TIMEOUT_SECONDS,
    }
    assert MESHTASTIC_BROADCAST_TIMEOUT_SECONDS == 15


def test_meshtastic_broadcast_invalidates_cached_activity(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("signal_relay.home_assistant.urlopen", lambda *_args, **_kwargs: Response())
    client = HomeAssistantMeshtasticClient("http://home-assistant", "private-token", {})
    client._cached_status = {"recentActivity": []}
    client._cache_expires_at = 9999999999

    client.broadcast("Hello mesh")

    assert client._cached_status is None
    assert client._cache_expires_at == 0


class FixtureClient(HomeAssistantLabClient):
    def __init__(self, responses):
        super().__init__("http://home-assistant", "private-token", "sensor.private_temperature", "sensor.private_humidity", "sensor.private_air_quality", 1)
        self.responses = responses
        self.requests = []

    def _get_json(self, path):
        self.requests.append(path)
        return self.responses[path]


def test_status_rounds_signals_and_keeps_them_cached():
    client = FixtureClient({
        "/api/": {"message": "API running."},
        "/api/states/sensor.private_temperature": {
            "state": "21.6", "attributes": {"device_class": "temperature", "unit_of_measurement": "°C", "friendly_name": "Private room"},
        },
        "/api/states/sensor.private_humidity": {
            "state": "42", "attributes": {"device_class": "humidity", "unit_of_measurement": "%", "friendly_name": "Private room"},
        },
        "/api/states/sensor.private_air_quality": {
            "state": "8", "attributes": {"device_class": "pm25", "unit_of_measurement": "µg/m³"},
        },
    })

    first = client.status()
    second = client.status()

    assert first["status"] == "available"
    assert first["temperatureC"] == 22
    assert first["humidityPercent"] == 40
    assert first["airQuality"] == "good"
    assert set(first) == {"status", "temperatureC", "humidityPercent", "airQuality", "refreshedAt"}
    assert second == first
    assert client.cache_seconds == 900
    assert client.requests == [
        "/api/",
        "/api/states/sensor.private_temperature",
        "/api/states/sensor.private_humidity",
        "/api/states/sensor.private_air_quality",
    ]


def test_status_rejects_an_unexpected_unit():
    client = FixtureClient({
        "/api/": {"message": "API running."},
        "/api/states/sensor.private_temperature": {
            "state": "71", "attributes": {"device_class": "temperature", "unit_of_measurement": "°F"},
        },
        "/api/states/sensor.private_humidity": {
            "state": "42", "attributes": {"device_class": "humidity", "unit_of_measurement": "%"},
        },
        "/api/states/sensor.private_air_quality": {
            "state": "8", "attributes": {"device_class": "pm25", "unit_of_measurement": "µg/m³"},
        },
    })

    with pytest.raises(ValueError, match="unexpected_home_assistant_unit"):
        client.status()


def test_status_accepts_home_assistants_greek_mu_pm25_unit():
    client = FixtureClient({
        "/api/": {"message": "API running."},
        "/api/states/sensor.private_temperature": {
            "state": "22", "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"},
        },
        "/api/states/sensor.private_humidity": {
            "state": "45", "attributes": {"device_class": "humidity", "unit_of_measurement": "%"},
        },
        "/api/states/sensor.private_air_quality": {
            "state": "18", "attributes": {"device_class": "pm25", "unit_of_measurement": "μg/m³"},
        },
    })

    assert client.status()["airQuality"] == "regular"


def test_meshtastic_status_normalizes_unavailable_values_and_hides_entity_metadata():
    entity_ids = {
        "gateway": "meshtastic.gateway",
        "node_long_name": "sensor.node_long_name",
        "node_short_name": "sensor.node_short_name",
        "uptime_seconds": "sensor.uptime",
        "battery_percent": "sensor.battery",
        "voltage": "sensor.voltage",
        "channel_utilization_percent": "sensor.channel",
        "airtime_tx_percent": "sensor.airtime",
        "nodes_online": "sensor.online",
        "nodes_total": "sensor.total",
        "packets_rx": "sensor.rx",
        "packets_tx": "sensor.tx",
        "packets_rx_bad": "sensor.rx_bad",
        "packets_rx_duplicate": "sensor.duplicate",
        "packets_tx_relayed": "sensor.relayed",
        "packets_tx_relay_cancelled": "sensor.relay_cancelled",
        "rx_per_minute": "sensor.rx_rate",
        "tx_per_minute": "sensor.tx_rate",
        "rf_errors_per_minute": "sensor.error_rate",
        "duplicates_per_minute": "sensor.duplicate_rate",
        "relay_cancelled_per_minute": "sensor.cancelled_rate",
        **{f"recent_activity_{index}": f"input_text.recent_activity_{index}" for index in range(1, 6)},
    }

    class FixtureMeshtasticClient(HomeAssistantMeshtasticClient):
        def __init__(self):
            super().__init__("http://home-assistant", "private-token", entity_ids, 15)
            self.requests = []

        def _get_json(self, path):
            self.requests.append(path)
            key = next(key for key, entity_id in entity_ids.items() if path.endswith(entity_id))
            states = {
                "gateway": "Connected",
                "node_long_name": "d3st gateway",
                "node_short_name": "d3st",
                "uptime_seconds": "120",
                "battery_percent": "101",
                "voltage": "4.12",
                "channel_utilization_percent": "unknown",
                "airtime_tx_percent": "2.5",
                "nodes_online": "3",
                "nodes_total": "5",
                "packets_rx": "10",
                "packets_tx": "9",
                "packets_rx_bad": "0",
                "packets_rx_duplicate": "1",
                "packets_tx_relayed": "2",
                "packets_tx_relay_cancelled": "0",
                "rx_per_minute": "0.4",
                "tx_per_minute": "0.2",
                "rf_errors_per_minute": "0",
                "duplicates_per_minute": "0.1",
                "relay_cancelled_per_minute": "unknown",
                "recent_activity_1": '{"message":"Hello mesh","sender":"Node One","receivedAt":"2026-10-01T12:00:00Z"}',
                "recent_activity_2": '{"message":"Previous message","sender":"Node Two","receivedAt":"2026-10-01T11:00:00Z"}',
                "recent_activity_3": "unknown",
                "recent_activity_4": "",
                "recent_activity_5": "not-json",
            }
            return {"state": states[key], "attributes": {"friendly_name": "Private metadata"}}

    status = FixtureMeshtasticClient().status()

    assert status["status"] == "available"
    assert status["gateway"] == {
        "name": "d3st gateway", "shortName": "d3st", "uptimeSeconds": 120, "batteryPercent": None, "voltage": 4.12,
    }
    assert status["network"]["channelUtilizationPercent"] is None
    assert status["recentActivity"] == [
        {"message": "Hello mesh", "sender": "Node One", "channel": "MediumFast", "receivedAt": "2026-10-01T12:00:00Z"},
        {"message": "Previous message", "sender": "Node Two", "channel": "MediumFast", "receivedAt": "2026-10-01T11:00:00Z"},
    ]
    assert "entity_id" not in str(status)


def test_meshtastic_status_hides_invalid_recent_activity():
    entity_ids = {
        "gateway": "meshtastic.gateway",
        "node_long_name": "sensor.node_long_name",
        "node_short_name": "sensor.node_short_name",
        "uptime_seconds": "sensor.uptime",
        "battery_percent": "sensor.battery",
        "voltage": "sensor.voltage",
        "channel_utilization_percent": "sensor.channel",
        "airtime_tx_percent": "sensor.airtime",
        "nodes_online": "sensor.online",
        "nodes_total": "sensor.total",
        "packets_rx": "sensor.rx",
        "packets_tx": "sensor.tx",
        "packets_rx_bad": "sensor.rx_bad",
        "packets_rx_duplicate": "sensor.duplicate",
        "packets_tx_relayed": "sensor.relayed",
        "packets_tx_relay_cancelled": "sensor.relay_cancelled",
        "rx_per_minute": "sensor.rx_rate",
        "tx_per_minute": "sensor.tx_rate",
        "rf_errors_per_minute": "sensor.error_rate",
        "duplicates_per_minute": "sensor.duplicate_rate",
        "relay_cancelled_per_minute": "sensor.cancelled_rate",
        **{f"recent_activity_{index}": f"input_text.recent_activity_{index}" for index in range(1, 6)},
    }

    class EmptyActivityClient(HomeAssistantMeshtasticClient):
        def _get_json(self, path):
            key = next(key for key, entity_id in entity_ids.items() if path.endswith(entity_id))
            states = {entity_key: "0" for entity_key in entity_ids}
            states["gateway"] = "Connected"
            states["recent_activity_1"] = "unknown"
            return {"state": states[key]}

    assert EmptyActivityClient("http://home-assistant", "private-token", entity_ids).status()["recentActivity"] == []