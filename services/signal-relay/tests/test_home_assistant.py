import pytest

from signal_relay.home_assistant import HomeAssistantLabClient, HomeAssistantMeshtasticClient


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
        "last_message": "input_text.message",
        "last_sender": "input_text.sender",
        "last_channel": "input_text.channel",
        "last_received": "input_datetime.received",
        "last_sender_hops": "input_number.hops",
        "last_sender_hops_available": "input_boolean.hops_available",
        "neighbor_long_name": "sensor.neighbor_long_name",
        "neighbor_short_name": "sensor.neighbor_short_name",
        "neighbor_snr": "sensor.neighbor_snr",
        "neighbor_hops_away": "sensor.neighbor_hops_away",
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
                "last_message": "Hello mesh",
                "last_sender": "Node One",
                "last_channel": "MediumFast",
                "last_received": "2026-10-01 12:00:00",
                "last_sender_hops": "2",
                "last_sender_hops_available": "on",
                "neighbor_long_name": "Neighbor One",
                "neighbor_short_name": "N1",
                "neighbor_snr": "7.5",
                "neighbor_hops_away": "1",
            }
            return {"state": states[key], "attributes": {"friendly_name": "Private metadata"}}

    status = FixtureMeshtasticClient().status()

    assert status["status"] == "available"
    assert status["gateway"] == {
        "name": "d3st gateway", "shortName": "d3st", "uptimeSeconds": 120, "batteryPercent": None, "voltage": 4.12,
    }
    assert status["network"]["channelUtilizationPercent"] is None
    assert status["neighbors"] == [{"name": "Neighbor One", "shortName": "N1", "snr": 7.5, "hopsAway": 1}]
    assert status["latestActivity"]["senderHopsAway"] == 2
    assert "entity_id" not in str(status)


def test_meshtastic_status_hides_empty_home_assistant_helpers():
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
        "last_message": "input_text.message",
        "last_sender": "input_text.sender",
        "last_channel": "input_text.channel",
        "last_received": "input_datetime.received",
        "last_sender_hops": "input_number.hops",
        "last_sender_hops_available": "input_boolean.hops_available",
        "neighbor_long_name": "sensor.neighbor_long_name",
        "neighbor_short_name": "sensor.neighbor_short_name",
        "neighbor_snr": "sensor.neighbor_snr",
        "neighbor_hops_away": "sensor.neighbor_hops_away",
    }

    class EmptyActivityClient(HomeAssistantMeshtasticClient):
        def _get_json(self, path):
            key = next(key for key, entity_id in entity_ids.items() if path.endswith(entity_id))
            states = {entity_key: "0" for entity_key in entity_ids}
            states["gateway"] = "Connected"
            states["last_message"] = "unknown"
            states["last_sender"] = "unknown"
            states["last_channel"] = "unknown"
            states["last_received"] = "unknown"
            return {"state": states[key]}

    assert EmptyActivityClient("http://home-assistant", "private-token", entity_ids).status()["latestActivity"] is None