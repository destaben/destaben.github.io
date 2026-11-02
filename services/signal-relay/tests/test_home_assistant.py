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

    def _get_list(self, path):
        self.requests.append(path)
        response = self.responses[path]
        if isinstance(response, Exception):
            raise response
        if not isinstance(response, list):
            raise ValueError("invalid_home_assistant_response")
        return response


class FixtureClient(ResponsesMixin, HomeAssistantLabClient):
    def __init__(self, responses, cache_seconds=1):
        super().__init__("http://home-assistant", "private-token", "sensor.private_temperature", "sensor.private_humidity", "sensor.private_air_quality", cache_seconds)
        self.responses = responses
        self.requests = []


GATEWAY = "meshtastic.gateway_private"
CHANNEL_PREFIX = "meshtastic.gateway_private_channel_"
# Attribute names are placeholders for the test fixtures; the real ones are verified on the host.
MESH_FIELDS = {"text": "message", "node_id": "from_id", "hop_start": "hop_start", "hop_limit": "hop_limit"}


class FixtureMeshtastic(ResponsesMixin, MeshtasticLabClient):
    def __init__(self, responses, *, cache_seconds=1, **options):
        options.setdefault("channel_fields", MESH_FIELDS)
        super().__init__(
            "http://home-assistant", "private-token", GATEWAY,
            "sensor.private_online", "sensor.private_total",
            cache_seconds, **options,
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
        "/api/states": [],
    }
    responses.update(overrides or {})
    return responses


def mesh_state(entity_id, state, attributes=None, last_changed="2026-11-02T09:15:03+00:00"):
    return {"entity_id": entity_id, "state": state, "attributes": {} if attributes is None else attributes, "last_changed": last_changed}


def message_attributes(**overrides):
    attributes = {"message": "Hello mesh", "from_id": "!7e5d1a42", "hop_start": 3, "hop_limit": 1}
    attributes.update(overrides)
    return attributes


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


def test_meshtastic_status_projects_counts_and_the_last_message_of_each_discovered_channel():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes())],
    }))

    status = client.status()

    assert status["status"] == "available"
    assert status["onlineNodes"] == 12
    assert status["totalNodes"] == 43
    assert set(status) == {"status", "onlineNodes", "totalNodes", "channels", "refreshedAt"}
    assert status["channels"] == [{
        "name": "Longfast",
        "last": {"nodeId": "!7e5d1a**", "text": "Hello mesh", "time": "2026-11-02T09:15:03Z", "hops": 2},
    }]
    assert set(status["channels"][0]) == {"name", "last"}
    assert set(status["channels"][0]["last"]) == {"nodeId", "text", "time", "hops"}
    # Channel states arrive with the single list read; no per-channel request is needed.
    assert client.requests == ["/api/", "/api/states/meshtastic.gateway_private", "/api/states/sensor.private_online", "/api/states/sensor.private_total", "/api/states"]


def test_meshtastic_status_publishes_an_empty_channel_list_when_none_are_discovered():
    status = FixtureMeshtastic(meshtastic_responses()).status()

    assert status["channels"] == []


def test_meshtastic_projection_never_contains_author_names_serials_macs_full_node_ids_or_entity_ids():
    attributes = message_attributes(
        long_name="SENTINEL-AUTHOR Name", short_name="SAUTH", from_name="SENTINEL-AUTHOR Name",
        serial="SENTINEL-SERIAL-7781", mac_address="SENTINEL-MAC-02:AB:CD",
        node_info={"serial": "SENTINEL-SERIAL-7781", "id": "!7e5d1a42"},
        previous_message="SENTINEL-OLDER-MESSAGE", friendly_name="Longfast",
    )
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", attributes)],
    }))

    rendered = json.dumps(client.status())

    for sentinel in ("SENTINEL", "SAUTH", "SERIAL", "MAC", "!7e5d1a42", "7e5d1a42", "meshtastic.", "sensor.private", "gateway_private"):
        assert sentinel not in rendered, sentinel


@pytest.mark.parametrize("entity_suffix, attributes", [
    ("direct_messages", {}),
    ("dm_alice", {}),
    ("dms", {}),
    ("private", {}),
    ("longfast", {"friendly_name": "Direct messages with SENTINEL-ALICE"}),
    ("longfast", {"friendly_name": "Private chat SENTINEL-ALICE"}),
    ("longfast", {"friendly_name": 42}),
    ("longfast", {"friendly_name": None}),
])
def test_direct_message_entities_are_never_published(entity_suffix, attributes):
    state = {"entity_id": CHANNEL_PREFIX + entity_suffix, "state": "SENTINEL-DM-TEXT", "attributes": {**message_attributes(), **attributes}, "last_changed": "2026-11-02T09:15:03+00:00"}
    client = FixtureMeshtastic(meshtastic_responses({"/api/states": [state]}))

    status = client.status()
    rendered = json.dumps(status)

    assert status["channels"] == []
    assert "SENTINEL" not in rendered


def test_direct_messages_are_excluded_while_public_channels_are_kept_alongside_them():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [
            mesh_state(CHANNEL_PREFIX + "direct_messages", "SENTINEL-DM-TEXT", message_attributes()),
            mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes()),
        ],
    }))

    status = client.status()

    assert [channel["name"] for channel in status["channels"]] == ["Longfast"]
    assert "SENTINEL" not in json.dumps(status)


def test_channel_names_that_only_resemble_direct_message_tokens_are_kept():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "dmitri", "Hello mesh", message_attributes())],
    }))

    assert [channel["name"] for channel in client.status()["channels"]] == ["Dmitri"]


def test_channel_denylist_matches_display_names_and_slugs_case_insensitively():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [
            mesh_state(CHANNEL_PREFIX + "telemetry", "one", message_attributes()),
            mesh_state(CHANNEL_PREFIX + "secret_room", "two", message_attributes()),
            mesh_state(CHANNEL_PREFIX + "longfast", "three", message_attributes()),
        ],
    }), channel_denylist={"TELEMETRY", "Secret Room"})

    assert [channel["name"] for channel in client.status()["channels"]] == ["Longfast"]


def test_only_valid_entity_ids_under_the_prefix_are_considered():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [
            mesh_state("sensor.unrelated_channel_longfast", "SENTINEL-OTHER", message_attributes()),
            {"entity_id": CHANNEL_PREFIX + "Upper", "state": "SENTINEL-UPPER", "attributes": message_attributes(), "last_changed": "2026-11-02T09:15:03+00:00"},
            "not an object",
            {"state": "no entity id"},
            mesh_state(CHANNEL_PREFIX + "ok", "Hello mesh", message_attributes()),
        ],
    }))

    status = client.status()

    assert [channel["name"] for channel in status["channels"]] == ["Ok"]
    assert "SENTINEL" not in json.dumps(status)


@pytest.mark.parametrize("prefix, entity_id", [
    ("meshtastic.gateway_private", GATEWAY),
    ("sensor.private_", "sensor.private_online"),
    ("sensor.private_", "sensor.private_total"),
])
def test_the_gateway_and_count_entities_are_never_treated_as_channels(prefix, entity_id):
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(entity_id, "12", message_attributes())],
    }), channel_prefix=prefix)

    assert client.status()["channels"] == []


def test_channels_without_a_usable_name_are_dropped_and_long_names_are_truncated():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [
            mesh_state(CHANNEL_PREFIX.rstrip("_"), "one", message_attributes()),
            mesh_state(CHANNEL_PREFIX, "two", message_attributes()),
            mesh_state(CHANNEL_PREFIX + "___", "three", message_attributes()),
            mesh_state(CHANNEL_PREFIX + "x" * 40, "four", message_attributes()),
        ],
    }))

    names = [channel["name"] for channel in client.status()["channels"]]

    assert names == ["X" + "x" * 31]
    assert all(name.isprintable() and len(name) <= 32 for name in names)


def test_at_most_sixteen_channels_are_published_in_entity_id_order():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(f"{CHANNEL_PREFIX}c{index:02d}", "hi", message_attributes()) for index in reversed(range(20))],
    }))

    names = [channel["name"] for channel in client.status()["channels"]]

    assert names == [f"C{index:02d}" for index in range(16)]


@pytest.mark.parametrize("node_id", ["Alice", "7e5d1a42", "!7e5d1a4", "!7e5d1a420", "!7e5d1a4g", "!7e5d1a42 ", 42, None, ["!7e5d1a42"]])
def test_last_message_is_omitted_without_a_valid_node_id_but_the_channel_is_kept(node_id):
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes(from_id=node_id))],
    }))

    status = client.status()

    assert status["channels"] == [{"name": "Longfast"}]


def test_node_ids_are_masked_by_replacing_their_last_two_characters():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes(from_id="!ABCDEF12"))],
    }))

    assert client.status()["channels"][0]["last"]["nodeId"] == "!ABCDEF**"


def test_no_last_message_is_published_when_the_node_id_field_is_not_configured():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes())],
    }), channel_fields={})

    assert client.status()["channels"] == [{"name": "Longfast"}]


def test_message_text_comes_from_the_entity_state_when_no_text_field_is_configured():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "State text", message_attributes())],
    }), channel_fields={"node_id": "from_id"})

    assert client.status()["channels"][0]["last"]["text"] == "State text"


def test_message_text_is_sanitized_and_truncated_to_two_hundred_characters():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [
            mesh_state(CHANNEL_PREFIX + "a", "x", message_attributes(message="  Hello\x07\tmesh\n  wor​ld  ")),
            mesh_state(CHANNEL_PREFIX + "b", "x", message_attributes(message="y" * 250)),
        ],
    }))

    channels = {channel["name"]: channel for channel in client.status()["channels"]}

    assert channels["A"]["last"]["text"] == "Hello mesh world"
    assert channels["B"]["last"]["text"] == "y" * 200


@pytest.mark.parametrize("message", ["unavailable", "Unknown", "none", "", "   \t ", "\x07\x1b", 42, None, ["Hello"]])
def test_invalid_message_text_drops_the_last_message_but_keeps_the_channel(message):
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello", message_attributes(message=message))],
    }))

    assert client.status()["channels"] == [{"name": "Longfast"}]


def test_missing_message_text_attribute_drops_the_last_message():
    attributes = message_attributes()
    del attributes["message"]
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello", attributes)],
    }))

    assert client.status()["channels"] == [{"name": "Longfast"}]


def test_message_time_is_the_timestamp_field_when_configured_and_last_changed_otherwise():
    fields = {**MESH_FIELDS, "timestamp": "rx_time"}
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [
            mesh_state(CHANNEL_PREFIX + "a", "x", message_attributes(rx_time="2026-11-02T10:00:00+01:00")),
            mesh_state(CHANNEL_PREFIX + "b", "x", message_attributes(rx_time="not a time"), last_changed="2026-11-02T11:20:30.654321+00:00"),
            mesh_state(CHANNEL_PREFIX + "c", "x", message_attributes(rx_time=1793_000_000)),
            mesh_state(CHANNEL_PREFIX + "d", "x", message_attributes(rx_time="2026-11-02T09:15:03"), last_changed="2026-11-02T11:20:30.654321+00:00"),
        ],
    }), channel_fields=fields)

    times = {channel["name"]: channel["last"]["time"] for channel in client.status()["channels"]}

    assert times["A"] == "2026-11-02T09:00:00Z"
    assert times["B"] == "2026-11-02T11:20:30Z"
    assert times["C"] == "2026-10-26T07:33:20Z"
    assert times["D"] == "2026-11-02T11:20:30Z"


def test_message_time_comes_from_last_changed_as_utc_without_microseconds():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello", message_attributes(), last_changed="2026-11-02T10:15:03.654321+01:00")],
    }))

    assert client.status()["channels"][0]["last"]["time"] == "2026-11-02T09:15:03Z"


@pytest.mark.parametrize("start, limit, expected", [(3, 1, 2), (7, 0, 7), (0, 0, 0), (2, 2, 0)])
def test_hops_are_hop_start_minus_hop_limit_when_both_are_exposed(start, limit, expected):
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello", message_attributes(hop_start=start, hop_limit=limit))],
    }))

    assert client.status()["channels"][0]["last"]["hops"] == expected


def test_hops_are_omitted_when_the_attributes_are_absent():
    attributes = message_attributes()
    del attributes["hop_start"]
    del attributes["hop_limit"]
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello", attributes)],
    }))

    last = client.status()["channels"][0]["last"]

    assert "hops" not in last
    assert set(last) == {"nodeId", "text", "time"}


@pytest.mark.parametrize("start, limit", [(1, 3), (8, 0), (-1, 0), (True, 0), ("3", "1"), (3, None), (3.0, 1)])
def test_inconsistent_hop_values_omit_hops_without_dropping_the_message(start, limit):
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello", message_attributes(hop_start=start, hop_limit=limit))],
    }))

    last = client.status()["channels"][0]["last"]

    assert "hops" not in last
    assert last["text"] == "Hello mesh"


@pytest.mark.parametrize("state", ["unavailable", "unknown", "disconnected", ""])
def test_disconnected_gateway_fails_the_projection_even_when_channels_are_listed(state):
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states/meshtastic.gateway_private": {"state": state},
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello", message_attributes())],
    }))

    with pytest.raises(ValueError, match="meshtastic_gateway_unavailable"):
        client.status()


def test_channel_discovery_failures_omit_channels_without_failing_the_counts():
    for failure in (URLError("refused"), HTTPError("http://home-assistant/api/states", 500, "Failure", None, None), {"not": "a list"}):
        client = FixtureMeshtastic(meshtastic_responses({"/api/states": failure}))

        status = client.status()

        assert status["status"] == "available"
        assert status["onlineNodes"] == 12
        assert status["totalNodes"] == 43
        assert "channels" not in status


def test_a_malformed_state_in_the_discovery_list_is_skipped_without_losing_other_channels():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [None, {"entity_id": CHANNEL_PREFIX + "broken", "state": "x", "attributes": "not a dict"}, mesh_state(CHANNEL_PREFIX + "longfast", "Hello", message_attributes())],
    }))

    assert [channel["name"] for channel in client.status()["channels"]] == ["Longfast"]


def test_channel_discovery_that_starts_after_the_refresh_deadline_omits_channels(clock, monkeypatch):
    responses = meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello", message_attributes())],
    })
    requested = []
    # The total count read runs past the 10 second refresh deadline, so the channel list is never started.
    costs = {"/api/states/sensor.private_total": 10.5}

    def slow_urlopen(request, timeout):
        requested.append(request.selector)
        clock.now += costs.get(request.selector, 0)
        return FakeHTTPResponse(json.dumps(responses[request.selector]).encode())

    monkeypatch.setattr(home_assistant, "urlopen", slow_urlopen)
    client = MeshtasticLabClient(
        "http://home-assistant", "private-token", GATEWAY, "sensor.private_online", "sensor.private_total",
        channel_fields=MESH_FIELDS,
    )

    status = client.status()

    assert status["totalNodes"] == 43
    assert "channels" not in status
    assert "/api/states" not in requested


def test_channels_are_discovered_with_one_entity_list_read(monkeypatch):
    requested = []
    responses = meshtastic_responses({"/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello", message_attributes())]})

    def fake_urlopen(request, timeout):
        requested.append(request.selector)
        return FakeHTTPResponse(json.dumps(responses[request.selector]).encode())

    monkeypatch.setattr(home_assistant, "urlopen", fake_urlopen)
    client = MeshtasticLabClient(
        "http://home-assistant", "private-token", GATEWAY, "sensor.private_online", "sensor.private_total",
        channel_fields=MESH_FIELDS,
    )

    client.status()

    assert requested.count("/api/states") == 1
    assert "/api/states/sensor.private_online" in requested


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


def test_meshtastic_status_is_cached_for_at_least_fifteen_minutes(clock):
    client = FixtureMeshtastic(meshtastic_responses(), cache_seconds=60)

    assert client.cache_seconds == 900
    first = client.status()
    clock.now += 899
    assert client.status() == first
    assert len(client.requests) == 5
    clock.now += 1
    client.status()
    assert len(client.requests) == 10


def test_meshtastic_failed_refresh_is_cached_briefly_and_reraises_the_same_error_class(clock):
    online = "/api/states/sensor.private_online"
    responses = meshtastic_responses({online: URLError("refused")})
    client = FixtureMeshtastic(responses)

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
    client = FixtureMeshtastic(meshtastic_responses())
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

    # "/api/", gateway, online, total, and the channel list: one refresh for all eight callers.
    assert len(client.requests) == warm_requests + 5
    assert all(result == results[0] for result in results)


def test_fresh_cache_hits_do_not_take_the_refresh_lock(clock):
    client = FixtureMeshtastic(meshtastic_responses(), cache_seconds=60)
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
    lambda: MeshtasticLabClient("http://home-assistant/", "private-token", "meshtastic.gw", "sensor.a", "sensor.b"),
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


def test_entity_list_reads_must_be_json_arrays(monkeypatch):
    monkeypatch.setattr(home_assistant, "urlopen", lambda request, timeout: FakeHTTPResponse(b'{"entity_id": "sensor.a"}'))
    client = MeshtasticLabClient("http://home-assistant/", "private-token", "meshtastic.gw", "sensor.a", "sensor.b")

    with pytest.raises(ValueError, match="invalid_home_assistant_response"):
        client._get_list("/api/states")


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
