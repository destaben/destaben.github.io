from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import re
import threading
import time
from urllib.error import HTTPError, URLError

import pytest

from signal_relay import home_assistant
from signal_relay.home_assistant import (
    MESHTASTIC_BROADCAST_TIMEOUT_SECONDS,
    HomeAssistantLabClient,
    HomeAssistantMeshtasticClient,
    MeshtasticLabClient,
)


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


# Channels are published only when named here; the fixture allowlists the names the channel tests expect to appear.
TEST_CHANNEL_ALLOWLIST = ("Longfast", "A", "B", "C", "D", "Ok", "Dmitri", "Telemetry", "Secret Room")


class FixtureMeshtastic(ResponsesMixin, MeshtasticLabClient):
    def __init__(self, responses, *, cache_seconds=1, **options):
        options.setdefault("channel_fields", MESH_FIELDS)
        options.setdefault("channel_allowlist", TEST_CHANNEL_ALLOWLIST)
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
        "/api/states/meshtastic.gateway_private": {"state": "Connected"},
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


def test_meshtastic_status_rejects_a_disconnected_gateway():
    client = FixtureMeshtastic(meshtastic_responses({"/api/states/meshtastic.gateway_private": {"state": "disconnected"}}))

    with pytest.raises(ValueError, match="meshtastic_gateway_unavailable"):
        client.status()


@pytest.mark.parametrize("state", [None, True, 42, "connected", "disconnected"])
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


def test_the_default_channel_prefix_is_derived_from_the_gateway_entity():
    client = MeshtasticLabClient("http://home-assistant", "private-token", GATEWAY, "sensor.private_online", "sensor.private_total")

    assert client.channel_prefix == CHANNEL_PREFIX


def test_channels_without_a_usable_name_are_dropped_and_long_names_are_truncated():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [
            mesh_state(CHANNEL_PREFIX.rstrip("_"), "one", message_attributes()),
            mesh_state(CHANNEL_PREFIX, "two", message_attributes()),
            mesh_state(CHANNEL_PREFIX + "___", "three", message_attributes()),
            mesh_state(CHANNEL_PREFIX + "x" * 40, "four", message_attributes()),
        ],
    }), channel_allowlist=("X" + "x" * 31, "Longfast"))

    names = [channel["name"] for channel in client.status()["channels"]]

    assert names == ["X" + "x" * 31]
    assert all(name.isprintable() and len(name) <= 32 for name in names)


def test_at_most_sixteen_channels_are_published_in_entity_id_order():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(f"{CHANNEL_PREFIX}c{index:02d}", "hi", message_attributes()) for index in reversed(range(20))],
    }), channel_allowlist=[f"c{index:02d}" for index in range(20)])

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
    # Each read stays inside its own 5 second body budget, but the reads together reach 11 seconds, past the
    # 10 second refresh deadline, so the channel list is never started.
    costs = {"/api/": 4, "/api/states/sensor.private_online": 4, "/api/states/sensor.private_total": 3}

    def slow_urlopen(request, timeout):
        requested.append(request.selector)
        clock.now += costs.get(request.selector, 0)
        return FakeHTTPResponse(json.dumps(responses[request.selector]).encode())

    monkeypatch.setattr(home_assistant, "urlopen", slow_urlopen)
    client = MeshtasticLabClient(
        "http://home-assistant", "private-token", GATEWAY, "sensor.private_online", "sensor.private_total",
        channel_fields=MESH_FIELDS, channel_allowlist=("Longfast",),
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
        channel_fields=MESH_FIELDS, channel_allowlist=("Longfast",),
    )

    client.status()

    assert requested.count("/api/states") == 1
    assert "/api/states/sensor.private_online" in requested


def test_a_dm_like_entity_named_after_a_person_is_not_published_unless_allowlisted():
    # No direct-message token appears in this name, so only the allowlist keeps it private.
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "alice_phone", "SENTINEL-ALICE-TEXT", message_attributes(friendly_name="Alice"))],
    }), channel_allowlist=("Longfast",))

    status = client.status()

    assert status["channels"] == []
    assert "SENTINEL" not in json.dumps(status)
    assert "Alice" not in json.dumps(status)


def test_only_allowlisted_channels_are_published():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [
            mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes()),
            mesh_state(CHANNEL_PREFIX + "alice_phone", "SENTINEL-ALICE-TEXT", message_attributes(friendly_name="Alice")),
            mesh_state(CHANNEL_PREFIX + "family", "SENTINEL-FAMILY-TEXT", message_attributes()),
        ],
    }), channel_allowlist=("Longfast",))

    status = client.status()

    assert [channel["name"] for channel in status["channels"]] == ["Longfast"]
    assert status["channels"][0]["last"]["text"] == "Hello mesh"
    assert "SENTINEL" not in json.dumps(status)


def test_allowlist_entries_match_channel_names_after_normalization():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "field_team", "Hello", message_attributes())],
    }), channel_allowlist=("  FIELD team ",))

    assert [channel["name"] for channel in client.status()["channels"]] == ["Field team"]


def test_denylist_takes_precedence_over_the_allowlist():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes())],
    }), channel_allowlist=("Longfast",), channel_denylist={"LONGFAST"})

    assert client.status()["channels"] == []


def test_an_empty_allowlist_publishes_no_channels_and_reads_no_channel_list():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes())],
    }), channel_allowlist=())

    status = client.status()

    assert status["status"] == "available"
    assert "channels" not in status
    assert "/api/states" not in client.requests


@pytest.mark.parametrize("slug", [
    "directos", "directas", "privados", "privadas", "mensajes_directos", "directo_bob",
    "whisper_bob", "secret_chat", "private_chat", "pm_alice", "dms", "dm_alice", "direct_chat",
])
def test_direct_message_tokens_exclude_a_channel_even_when_it_is_allowlisted(slug):
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + slug, "SENTINEL-DM-TEXT", message_attributes())],
    }), channel_allowlist=(slug,))

    status = client.status()

    assert status["channels"] == []
    assert "SENTINEL" not in json.dumps(status)


def test_meshtastic_status_is_cached_for_at_least_fifteen_minutes(clock):
    client = FixtureMeshtastic(meshtastic_responses(), cache_seconds=60)

    assert client.cache_seconds == 900
    first = client.status()
    clock.now += 899
    assert client.status() == first
    # "/api/", gateway, online, total, and the channel list: one refresh.
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

    def read1(self, *args):
        # Serves the body once, like http.client.HTTPResponse.read1.
        body, self.body = self.body, b""
        return body


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


class OversizedResponse(FakeHTTPResponse):
    """Endless whitespace, so only the size cap can stop the read."""

    def __init__(self):
        super().__init__(b"")

    def read1(self, *args):
        return b" " * (64 * 1024)


class SlowDripResponse(FakeHTTPResponse):
    """One byte per call, with three seconds of fake time spent on each, like a slow-drip upstream."""

    def __init__(self, clock):
        super().__init__(b"")
        self.clock = clock

    def read1(self, *args):
        self.clock.now += 3
        return b" "


def test_home_assistant_bodies_are_capped_at_one_mebibyte(monkeypatch):
    monkeypatch.setattr(home_assistant, "urlopen", lambda request, timeout: OversizedResponse())

    with pytest.raises(ValueError, match="home_assistant_response_too_large"):
        home_assistant._read_json("http://home-assistant", "private-token", "/api/", 5)


def test_slow_drip_home_assistant_bodies_stop_once_the_read_budget_is_spent(clock, monkeypatch):
    monkeypatch.setattr(home_assistant, "urlopen", lambda request, timeout: SlowDripResponse(clock))
    started = clock.now

    with pytest.raises(ValueError, match="home_assistant_read_too_slow"):
        home_assistant._read_json("http://home-assistant", "private-token", "/api/", 5)
    # The budget is 5 s; the check runs after each chunk, so at most one chunk overruns it.
    assert clock.now - started <= 5 + 3


def test_slow_drip_refresh_releases_the_lock_within_the_documented_bound(clock, monkeypatch):
    monkeypatch.setattr(home_assistant, "urlopen", lambda request, timeout: SlowDripResponse(clock))
    client = HomeAssistantLabClient("http://home-assistant", "private-token", "sensor.a", "sensor.b", "sensor.c")
    started = clock.now

    with pytest.raises(ValueError, match="home_assistant_read_too_slow"):
        client.status()
    assert clock.now - started <= 5 + 3
    assert not client._refresh_lock.locked()


def test_home_assistant_bodies_are_read_through_the_real_redirect_refusing_opener():
    class State(_QuietHandler):
        def do_GET(self):
            body = b'{"state": "21.6"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _http_server(State) as port:
        payload = home_assistant._read_json(f"http://127.0.0.1:{port}", "private-token", "/api/states/sensor.a", 5)

    assert payload == {"state": "21.6"}


def test_truncated_home_assistant_responses_are_value_errors(monkeypatch):
    class TruncatedResponse(FakeHTTPResponse):
        def read1(self, *args):
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


def test_a_failed_channel_read_keeps_the_counts_cached_but_retries_channels_after_a_minute(clock):
    responses = meshtastic_responses({"/api/states": URLError("refused")})
    client = FixtureMeshtastic(responses)

    first = client.status()

    assert "channels" not in first
    responses["/api/states"] = [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes())]
    requests_after_first = len(client.requests)
    clock.now += 59
    # Within the partial window nothing is re-read, so the counts and the missing channels stay as they were.
    assert client.status() == first
    assert len(client.requests) == requests_after_first
    clock.now += 1
    second = client.status()
    assert [channel["name"] for channel in second["channels"]] == ["Longfast"]
    assert second["onlineNodes"] == first["onlineNodes"]
    assert len(client.requests) > requests_after_first


def test_a_successful_channel_read_keeps_the_full_status_window(clock):
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes())],
    }))
    first = client.status()
    requests = len(client.requests)

    clock.now += 899

    assert client.status() == first
    assert len(client.requests) == requests


@pytest.mark.parametrize("path", ["/api/states/sensor.private_online", "/api/states/sensor.private_total"])
@pytest.mark.parametrize("state", ["100001", 100001, "1000001"])
def test_node_counts_above_the_documented_limit_are_rejected(path, state):
    # Both counts start at the limit so that only the tested count can be the reason for the rejection.
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states/sensor.private_online": {"state": "100000"},
        "/api/states/sensor.private_total": {"state": "100000"},
        path: {"state": state},
    }))

    with pytest.raises(ValueError, match=r"^invalid_meshtastic_node_count$"):
        client.status()


def test_node_counts_at_the_documented_limit_are_accepted():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states/sensor.private_online": {"state": "100000"},
        "/api/states/sensor.private_total": {"state": "100000"},
    }))

    status = client.status()

    assert status["onlineNodes"] == 100000
    assert status["totalNodes"] == 100000


def test_gateway_friendly_name_words_are_ignored_for_direct_message_detection():
    # The gateway is named "Private Gateway", so its own words must not make every channel look private.
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states/meshtastic.gateway_private": {"state": "Connected", "attributes": {"friendly_name": "Private Gateway"}},
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes(friendly_name="Private Gateway Longfast"))],
    }), channel_allowlist=("Longfast",))

    assert [channel["name"] for channel in client.status()["channels"]] == ["Longfast"]


def test_a_private_word_that_is_not_the_gateway_name_still_excludes_the_channel():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states/meshtastic.gateway_private": {"state": "Connected", "attributes": {"friendly_name": "Private Gateway"}},
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "Hello mesh", message_attributes(friendly_name="Private chat"))],
    }), channel_allowlist=("Longfast",))

    assert client.status()["channels"] == []


def test_direct_message_words_in_a_custom_channel_prefix_exclude_the_channel():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state("sensor.dm_longfast", "SENTINEL-DM-TEXT", message_attributes())],
    }), channel_prefix="sensor.dm_", channel_allowlist=("Longfast",))

    status = client.status()

    assert status["channels"] == []
    assert "SENTINEL" not in json.dumps(status)


def test_the_relay_node_count_limit_is_the_documented_value():
    assert home_assistant._MAX_NODE_COUNT == 100_000



@pytest.mark.parametrize("text, expected", [
    ("ping !52302e42", "ping !52302e**"),
    ("!52302e42 and !7E5D1A42 both", "!52302e** and !7E5D1A** both"),
    ("ping !ABCDEF12.", "ping !ABCDEF**."),
    ("reach me at !abcdef12, thanks", "reach me at !abcdef**, thanks"),
    ("short !abc and bare 52302e42 stay", "short !abc and bare 52302e42 stay"),
])
def test_node_ids_inside_message_text_are_masked_like_the_sender_field(text, expected):
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "state", message_attributes(message=text))],
    }))

    channel = client.status()["channels"][0]

    assert channel["last"]["text"] == expected


def test_a_full_node_id_in_message_text_never_appears_in_the_projection():
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "state", message_attributes(message="ping !7e5d1a42 from !7E5D1A99"))],
    }))

    rendered = json.dumps(client.status())

    assert "!7e5d1a**" in rendered
    assert "!7E5D1A**" in rendered
    assert "7e5d1a42" not in rendered
    assert "7E5D1A99" not in rendered


@pytest.mark.parametrize("visible_hex", range(1, 9))
def test_a_node_id_straddling_the_message_limit_never_leaves_a_fragment(visible_hex):
    # The ID starts so that exactly `visible_hex` of its digits fall inside the 200-character limit.
    text = "x" * (199 - visible_hex) + "!52302e42" + " tail"
    client = FixtureMeshtastic(meshtastic_responses({
        "/api/states": [mesh_state(CHANNEL_PREFIX + "longfast", "state", message_attributes(message=text))],
    }))

    published = client.status()["channels"][0]["last"]["text"]

    assert len(published) <= 200
    assert "52302e42" not in published
    assert re.search(r"!52302e[0-9A-Fa-f]", published) is None
    if visible_hex == 8:
        # The whole ID fits, so it is masked like any other node ID.
        assert published == "x" * 191 + "!52302e**"
    else:
        # A partial ID at the cut is dropped entirely.
        assert published == "x" * (199 - visible_hex)
