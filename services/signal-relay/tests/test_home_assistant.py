from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import threading
import time
from urllib.error import HTTPError, URLError

import pytest

from signal_relay import home_assistant
from signal_relay.home_assistant import HomeAssistantLabClient, MeshtasticLabClient


class FakeClock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(home_assistant.time, "monotonic", fake)
    return fake


class ResponsesMixin:
    def _get_json(self, path):
        self.requests.append(path)
        response = self.responses[path]
        if isinstance(response, Exception):
            raise response
        return response


class FixtureClient(ResponsesMixin, HomeAssistantLabClient):
    def __init__(self, responses, cache_seconds=1):
        super().__init__("http://home-assistant", "private-token", "sensor.private_temperature", "sensor.private_humidity", "sensor.private_air_quality", cache_seconds)
        self.responses = responses
        self.requests = []


class FixtureMeshtastic(ResponsesMixin, MeshtasticLabClient):
    def __init__(self, responses, *, last_node=True, cache_seconds=1):
        super().__init__(
            "http://home-assistant", "private-token", "meshtastic.gateway_private",
            "sensor.private_online", "sensor.private_total",
            "sensor.private_last_node" if last_node else None,
            cache_seconds,
        )
        self.responses = responses
        self.requests = []


def home_responses(overrides=None):
    responses = {
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
    }
    responses.update(overrides or {})
    return responses


def meshtastic_responses(overrides=None):
    responses = {
        "/api/": {"message": "API running."},
        "/api/states/meshtastic.gateway_private": {"state": "connected"},
        "/api/states/sensor.private_online": {"state": "12"},
        "/api/states/sensor.private_total": {"state": "43"},
        "/api/states/sensor.private_last_node": {"state": "Field relay"},
    }
    responses.update(overrides or {})
    return responses


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


@pytest.mark.parametrize("path", [
    "/api/states/sensor.private_temperature",
    "/api/states/sensor.private_humidity",
    "/api/states/sensor.private_air_quality",
])
@pytest.mark.parametrize("state", [None, True, [], "", "abc", "nan", "inf"])
def test_home_assistant_states_must_be_finite_numbers(path, state):
    responses = home_responses()
    responses[path] = {**responses[path], "state": state}
    client = FixtureClient(responses)

    with pytest.raises(ValueError, match="invalid_home_assistant_value"):
        client.status()


def test_home_assistant_failed_refresh_is_cached_briefly_and_reraises_the_same_error_class(clock):
    humidity = "/api/states/sensor.private_humidity"
    responses = home_responses({humidity: URLError("timed out")})
    client = FixtureClient(responses)

    with pytest.raises(URLError):
        client.status()
    clock.now += 29
    with pytest.raises(URLError) as second:
        client.status()
    assert second.type is URLError
    assert client.requests.count(humidity) == 1

    responses[humidity] = home_responses()[humidity]
    clock.now += 1
    assert client.status()["humidityPercent"] == 40
    assert client.requests.count(humidity) == 2


def test_home_assistant_status_is_cached_for_at_least_fifteen_minutes(clock):
    client = FixtureClient(home_responses(), cache_seconds=60)

    assert client.cache_seconds == 900
    first = client.status()
    clock.now += 899
    assert client.status() == first
    assert len(client.requests) == 4
    clock.now += 1
    client.status()
    assert len(client.requests) == 8


def test_longer_cache_windows_are_respected(clock):
    client = FixtureClient(home_responses(), cache_seconds=3600)

    assert client.cache_seconds == 3600
    client.status()
    clock.now += 3599
    client.status()
    assert len(client.requests) == 4


def test_meshtastic_status_returns_only_aggregate_counts_and_configured_last_node():
    class FixtureMeshtastic(MeshtasticLabClient):
        def __init__(self):
            super().__init__(
                "http://home-assistant", "private-token", "meshtastic.gateway_private",
                "sensor.private_online", "sensor.private_total", "sensor.private_last_node", 1,
            )
            self.responses = {
                "/api/": {"message": "API running."},
                "/api/states/meshtastic.gateway_private": {"state": "connected"},
                "/api/states/sensor.private_online": {"state": "12"},
                "/api/states/sensor.private_total": {"state": "43"},
                "/api/states/sensor.private_last_node": {"state": "Field relay"},
            }

        def _get_json(self, path):
            return self.responses[path]

    status = FixtureMeshtastic().status()

    assert status["status"] == "available"
    assert status["onlineNodes"] == 12
    assert status["totalNodes"] == 43
    assert status["lastNode"] == "Field relay"
    assert set(status) == {"status", "onlineNodes", "totalNodes", "lastNode", "refreshedAt"}


def test_meshtastic_status_rejects_a_disconnected_gateway():
    class FixtureMeshtastic(MeshtasticLabClient):
        def __init__(self):
            super().__init__(
                "http://home-assistant", "private-token", "meshtastic.gateway_private",
                "sensor.private_online", "sensor.private_total", None, 1,
            )
            self.responses = {
                "/api/": {"message": "API running."},
                "/api/states/meshtastic.gateway_private": {"state": "disconnected"},
            }

        def _get_json(self, path):
            return self.responses[path]

    with pytest.raises(ValueError, match="meshtastic_gateway_unavailable"):
        FixtureMeshtastic().status()


@pytest.mark.parametrize("state", [None, True, 42])
def test_meshtastic_gateway_must_report_connected(state):
    client = FixtureMeshtastic(meshtastic_responses({"/api/states/meshtastic.gateway_private": {"state": state}}))

    with pytest.raises(ValueError, match="meshtastic_gateway_unavailable"):
        client.status()


@pytest.mark.parametrize("path", ["/api/states/sensor.private_online", "/api/states/sensor.private_total"])
@pytest.mark.parametrize("state", [None, True, [], "", "abc", "nan", "inf", "12.5", "-1"])
def test_meshtastic_counts_must_be_non_negative_integers(path, state):
    client = FixtureMeshtastic(meshtastic_responses({path: {"state": state}}))

    with pytest.raises(ValueError, match="invalid_meshtastic_node_count"):
        client.status()


def test_meshtastic_counts_accept_integral_values_from_home_assistant():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states/sensor.private_online": {"state": 12},
        "/api/states/sensor.private_total": {"state": "43.0"},
    }))

    status = client.status()

    assert status["onlineNodes"] == 12
    assert status["totalNodes"] == 43


def test_meshtastic_rejects_more_online_nodes_than_total_nodes_but_accepts_equal_counts():
    client = FixtureMeshtastic(meshtastic_responses({"/api/states/sensor.private_online": {"state": "44"}}))
    with pytest.raises(ValueError, match="invalid_meshtastic_node_counts"):
        client.status()

    equal = FixtureMeshtastic(meshtastic_responses({"/api/states/sensor.private_online": {"state": "43"}}))
    assert equal.status()["onlineNodes"] == 43


@pytest.mark.parametrize("state", ["unavailable", "Unavailable", "unknown", "none", "NONE", "", "   "])
def test_meshtastic_placeholder_last_node_states_are_omitted(state):
    client = FixtureMeshtastic(meshtastic_responses({"/api/states/sensor.private_last_node": {"state": state}}))

    status = client.status()

    assert status["status"] == "available"
    assert status["onlineNodes"] == 12
    assert "lastNode" not in status


@pytest.mark.parametrize("state", ["x" * 65, "Field\x07relay", "Field\x7frelay", "Field\x9brelay", None, 42, ["Field relay"]])
def test_meshtastic_invalid_last_node_names_are_omitted_without_failing_the_panel(state):
    client = FixtureMeshtastic(meshtastic_responses({"/api/states/sensor.private_last_node": {"state": state}}))

    status = client.status()

    assert status["status"] == "available"
    assert status["totalNodes"] == 43
    assert "lastNode" not in status


def test_meshtastic_last_node_is_whitespace_normalized_and_kept_at_64_characters():
    client = FixtureMeshtastic(meshtastic_responses({"/api/states/sensor.private_last_node": {"state": "  Field\trelay   node "}}))
    assert client.status()["lastNode"] == "Field relay node"

    exact = FixtureMeshtastic(meshtastic_responses({"/api/states/sensor.private_last_node": {"state": "x" * 64}}))
    assert exact.status()["lastNode"] == "x" * 64


def test_meshtastic_without_a_last_node_entity_does_not_request_one():
    client = FixtureMeshtastic(meshtastic_responses(), last_node=False)

    status = client.status()

    assert "lastNode" not in status
    assert "/api/states/sensor.private_last_node" not in client.requests


def test_meshtastic_last_node_transport_error_still_fails_the_projection():
    client = FixtureMeshtastic(meshtastic_responses({"/api/states/sensor.private_last_node": URLError("refused")}))

    with pytest.raises(URLError):
        client.status()


def test_meshtastic_last_node_404_omits_the_name_without_failing_the_projection():
    missing = HTTPError("http://home-assistant/api/states/sensor.private_last_node", 404, "Not Found", None, None)
    client = FixtureMeshtastic(meshtastic_responses({"/api/states/sensor.private_last_node": missing}))

    status = client.status()

    assert status["status"] == "available"
    assert status["onlineNodes"] == 12
    assert status["totalNodes"] == 43
    assert "lastNode" not in status


@pytest.mark.parametrize("code", [401, 500])
def test_meshtastic_last_node_other_http_errors_still_fail_the_projection(code):
    error = HTTPError("http://home-assistant/api/states/sensor.private_last_node", code, "Failure", None, None)
    client = FixtureMeshtastic(meshtastic_responses({"/api/states/sensor.private_last_node": error}))

    with pytest.raises(HTTPError):
        client.status()


def test_meshtastic_status_is_cached_for_at_least_fifteen_minutes(clock):
    client = FixtureMeshtastic(meshtastic_responses(), last_node=False, cache_seconds=60)

    assert client.cache_seconds == 900
    first = client.status()
    clock.now += 899
    assert client.status() == first
    assert len(client.requests) == 4
    clock.now += 1
    client.status()
    assert len(client.requests) == 8


def test_meshtastic_failed_refresh_is_cached_briefly_and_reraises_the_same_error_class(clock):
    online = "/api/states/sensor.private_online"
    responses = meshtastic_responses({online: URLError("refused")})
    client = FixtureMeshtastic(responses, last_node=False)

    with pytest.raises(URLError):
        client.status()
    clock.now += 29
    with pytest.raises(URLError) as second:
        client.status()
    assert second.type is URLError
    assert client.requests.count(online) == 1

    responses[online] = {"state": "12"}
    clock.now += 1
    assert client.status()["onlineNodes"] == 12
    assert client.requests.count(online) == 2


def test_concurrent_requests_refetch_once_when_the_cache_expires(clock):
    client = FixtureMeshtastic(meshtastic_responses(), last_node=False)
    client.status()
    warm_requests = len(client.requests)
    clock.now += 900

    upstream_get_json = client._get_json

    def slow_get_json(path):
        time.sleep(0.02)
        return upstream_get_json(path)

    client._get_json = slow_get_json
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: client.status(), range(8)))

    # "/api/", gateway, online, total: one refresh for all eight callers.
    assert len(client.requests) == warm_requests + 4
    assert all(result == results[0] for result in results)


def test_fresh_cache_hits_do_not_take_the_refresh_lock(clock):
    client = FixtureMeshtastic(meshtastic_responses(), last_node=False, cache_seconds=60)
    first = client.status()

    class ForbiddenLock:
        def __enter__(self):
            raise AssertionError("a fresh cache hit must not wait on the refresh lock")

        def __exit__(self, *exc_info):
            return False

    client._refresh_lock = ForbiddenLock()
    clock.now += 899

    assert client.status() == first


def test_refresh_stops_issuing_requests_after_its_deadline_and_caches_the_failure(clock, monkeypatch):
    responses = home_responses()
    requested = []
    seconds_per_request = {"value": 4}

    def slow_urlopen(request, timeout):
        requested.append(request.selector)
        clock.now += seconds_per_request["value"]
        return FakeHTTPResponse(json.dumps(responses[request.selector]).encode())

    monkeypatch.setattr(home_assistant, "urlopen", slow_urlopen)
    client = HomeAssistantLabClient(
        "http://home-assistant", "private-token",
        "sensor.private_temperature", "sensor.private_humidity", "sensor.private_air_quality",
    )

    # Each request costs 4 seconds, so the air quality read starts after the 10 second refresh deadline.
    with pytest.raises(ValueError, match="home_assistant_refresh_deadline_exceeded"):
        client.status()
    assert requested == [
        "/api/",
        "/api/states/sensor.private_temperature",
        "/api/states/sensor.private_humidity",
    ]

    clock.now += 1
    with pytest.raises(ValueError, match="home_assistant_refresh_deadline_exceeded"):
        client.status()
    assert len(requested) == 3

    seconds_per_request["value"] = 0
    clock.now += 30
    assert client.status()["airQuality"] == "good"
    assert len(requested) == 7


class FakeHTTPResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self, *args):
        return self.body


@pytest.mark.parametrize("make_client", [
    lambda: HomeAssistantLabClient("http://home-assistant/", "private-token", "sensor.a", "sensor.b", "sensor.c"),
    lambda: MeshtasticLabClient("http://home-assistant/", "private-token", "meshtastic.gw", "sensor.a", "sensor.b", None),
])
def test_shared_request_helper_sends_the_bearer_token_and_rejects_non_object_json(monkeypatch, make_client):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["authorization"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return FakeHTTPResponse(b'["not", "an", "object"]')

    monkeypatch.setattr(home_assistant, "urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="invalid_home_assistant_response"):
        make_client()._get_json("/api/")
    assert seen == {"authorization": "Bearer private-token", "timeout": 5}


def test_truncated_home_assistant_responses_are_value_errors(monkeypatch):
    class TruncatedResponse(FakeHTTPResponse):
        def read(self, *args):
            raise http.client.IncompleteRead(b'{"state"')

    monkeypatch.setattr(home_assistant, "urlopen", lambda request, timeout: TruncatedResponse(b""))
    client = HomeAssistantLabClient("http://home-assistant", "private-token", "sensor.a", "sensor.b", "sensor.c")

    with pytest.raises(ValueError, match="invalid_home_assistant_response"):
        client._get_json("/api/")


class _QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@contextmanager
def _http_server(handler_class):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_bearer_token_is_never_forwarded_across_a_redirect():
    seen_authorization = []

    class Elsewhere(_QuietHandler):
        def do_GET(self):
            seen_authorization.append(self.headers.get("Authorization"))
            body = b'{"message": "API running."}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _http_server(Elsewhere) as elsewhere_port:

        class Redirecting(_QuietHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", f"http://localhost:{elsewhere_port}/api/")
                self.send_header("Content-Length", "0")
                self.end_headers()

        with _http_server(Redirecting) as origin_port:
            client = HomeAssistantLabClient(
                f"http://127.0.0.1:{origin_port}", "private-token",
                "sensor.a", "sensor.b", "sensor.c",
            )
            with pytest.raises(ValueError, match="invalid_home_assistant_response"):
                client._get_json("/api/")

    assert seen_authorization == []
