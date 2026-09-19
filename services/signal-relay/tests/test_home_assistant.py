import pytest

from signal_relay.home_assistant import HomeAssistantLabClient


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