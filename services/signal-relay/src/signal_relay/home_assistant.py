from __future__ import annotations

from datetime import UTC, datetime
import http.client
import json
import math
import threading
import time
from typing import Mapping
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


MESHTASTIC_BROADCAST_TIMEOUT_SECONDS = 15
# Successful projections are deliberately delayed; configured cache windows can only extend this.
_MINIMUM_SUCCESS_CACHE_SECONDS = 900
# Failures are remembered briefly so a Home Assistant outage is not retried on every public request.
_FAILURE_CACHE_SECONDS = 30
_REQUEST_TIMEOUT_SECONDS = 5
# One refresh issues at most a handful of reads; no new read starts once this much time has passed.
_REFRESH_DEADLINE_SECONDS = 10
_MAX_NODE_NAME_LENGTH = 64
# Home Assistant placeholder states that mean "no usable name" rather than a name to publish.
_PLACEHOLDER_STATES = frozenset({"", "unavailable", "unknown", "none"})


def _finite_state(payload: dict[str, object], error_code: str) -> float:
    state = payload.get("state")
    if isinstance(state, bool) or not isinstance(state, (str, int, float)):
        raise ValueError(error_code)
    try:
        value = float(state)
    except (ValueError, OverflowError):
        raise ValueError(error_code) from None
    if not math.isfinite(value):
        raise ValueError(error_code)
    return value


class _RefuseRedirects(HTTPRedirectHandler):
    """A followed redirect would replay the Bearer token to another location, so it is an error instead."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("invalid_home_assistant_response")


_redirect_free_opener = build_opener(_RefuseRedirects)


def urlopen(request: Request, timeout: float):
    """Opens a Home Assistant request; redirects are refused so the Authorization header stays on this origin."""
    return _redirect_free_opener.open(request, timeout=timeout)


def _read_json(base_url: str, token: str, path: str, timeout: float) -> dict[str, object]:
    """One authenticated Home Assistant GET; shared by every client so the token handling lives in one place."""
    request = Request(
        f"{base_url}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except http.client.HTTPException as error:
        raise ValueError("invalid_home_assistant_response") from error
    if not isinstance(payload, dict):
        raise ValueError("invalid_home_assistant_response")
    return payload


class _HomeAssistantClient:
    """Shared authenticated reads, delayed success caching, and short failure caching."""

    def __init__(self, base_url: str, token: str, cache_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.cache_seconds = max(cache_seconds, _MINIMUM_SUCCESS_CACHE_SECONDS)
        # Held across the refresh so concurrent callers at expiry wait for one upstream fetch.
        self._refresh_lock = threading.Lock()
        # (expires_at, status) in one reference so a lock-free read never pairs a value with another expiry.
        self._fresh_status: tuple[float, dict[str, object]] | None = None
        self._cached_error: Exception | None = None
        self._error_expires_at = 0.0
        # Reads issued after this monotonic instant fail fast; set only while a refresh is running.
        self._refresh_deadline = math.inf

    def status(self) -> dict[str, object]:
        fresh = self._fresh_status
        if fresh is not None and time.monotonic() < fresh[0]:
            return fresh[1]
        with self._refresh_lock:
            # Re-check: another caller may have refreshed while this one waited for the lock.
            now = time.monotonic()
            fresh = self._fresh_status
            if fresh is not None and now < fresh[0]:
                return fresh[1]
            if self._cached_error is not None and now < self._error_expires_at:
                raise self._cached_error.with_traceback(None)
            self._refresh_deadline = now + _REFRESH_DEADLINE_SECONDS
            try:
                status = self._refresh()
            except Exception as error:
                self._cached_error = error
                self._error_expires_at = time.monotonic() + _FAILURE_CACHE_SECONDS
                raise
            finally:
                self._refresh_deadline = math.inf
            self._cached_error = None
            self._fresh_status = (time.monotonic() + self.cache_seconds, status)
            return status

    def _refresh(self) -> dict[str, object]:
        raise NotImplementedError

    def _state(self, entity_id: str) -> dict[str, object]:
        return self._get_json(f"/api/states/{entity_id}")

    def _get_json(self, path: str) -> dict[str, object]:
        if time.monotonic() >= self._refresh_deadline:
            raise ValueError("home_assistant_refresh_deadline_exceeded")
        return _read_json(self.base_url, self.token, path, _REQUEST_TIMEOUT_SECONDS)


class HomeAssistantLabClient(_HomeAssistantClient):
    """Projects two configured Home Assistant entities into a bounded public view."""

    def __init__(
        self,
        base_url: str,
        token: str,
        temperature_entity_id: str,
        humidity_entity_id: str,
        air_quality_entity_id: str,
        cache_seconds: int = 900,
    ) -> None:
        super().__init__(base_url, token, cache_seconds)
        self.temperature_entity_id = temperature_entity_id
        self.humidity_entity_id = humidity_entity_id
        self.air_quality_entity_id = air_quality_entity_id

    def _refresh(self) -> dict[str, object]:
        self._get_json("/api/")
        temperature = self._state_value(self.temperature_entity_id, "temperature", "°C")
        humidity = self._state_value(self.humidity_entity_id, "humidity", "%")
        air_quality = self._air_quality()
        refreshed_at = datetime.now(UTC).replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")
        return {
            "status": "available",
            "temperatureC": round(temperature),
            "humidityPercent": round(humidity / 5) * 5,
            "airQuality": air_quality,
            "refreshedAt": refreshed_at,
        }

    def _state_value(self, entity_id: str, expected_device_class: str, expected_unit: str) -> float:
        payload = self._state(entity_id)
        attributes = payload.get("attributes")
        if not isinstance(attributes, dict):
            raise ValueError("invalid_home_assistant_state")
        if attributes.get("device_class") != expected_device_class or attributes.get("unit_of_measurement") != expected_unit:
            raise ValueError("unexpected_home_assistant_unit")
        return _finite_state(payload, "invalid_home_assistant_value")

    def _air_quality(self) -> str:
        payload = self._state(self.air_quality_entity_id)
        attributes = payload.get("attributes")
        if not isinstance(attributes, dict):
            raise ValueError("invalid_home_assistant_state")
        device_class = attributes.get("device_class")
        unit = attributes.get("unit_of_measurement")
        value = _finite_state(payload, "invalid_home_assistant_value")
        if device_class == "pm25" and isinstance(unit, str) and unit.replace("μ", "µ") == "µg/m³":
            return "good" if value <= 12 else "regular" if value <= 35 else "bad"
        if device_class == "carbon_dioxide" and unit == "ppm":
            return "good" if value <= 800 else "regular" if value <= 1200 else "bad"
        raise ValueError("unsupported_air_quality_metric")


class MeshtasticLabClient(_HomeAssistantClient):
    """Publishes a deliberately small, read-only Meshtastic status projection."""

    def __init__(
        self,
        base_url: str,
        token: str,
        gateway_entity_id: str,
        nodes_online_entity_id: str,
        nodes_total_entity_id: str,
        last_node_entity_id: str | None,
        cache_seconds: int = 900,
    ) -> None:
        super().__init__(base_url, token, cache_seconds)
        self.gateway_entity_id = gateway_entity_id
        self.nodes_online_entity_id = nodes_online_entity_id
        self.nodes_total_entity_id = nodes_total_entity_id
        self.last_node_entity_id = last_node_entity_id

    def _refresh(self) -> dict[str, object]:
        self._get_json("/api/")
        # The gateway state casing matches the Meshtastic send projection, which reads the same entity.
        gateway_state = self._state(self.gateway_entity_id).get("state")
        if gateway_state != "Connected":
            raise ValueError("meshtastic_gateway_unavailable")
        online = self._count(self.nodes_online_entity_id)
        total = self._count(self.nodes_total_entity_id)
        if online > total:
            raise ValueError("invalid_meshtastic_node_counts")
        status: dict[str, object] = {
            "status": "available",
            "onlineNodes": online,
            "totalNodes": total,
            "refreshedAt": datetime.now(UTC).replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        if self.last_node_entity_id:
            last_node = self._optional_node_name(self.last_node_entity_id)
            if last_node is not None:
                status["lastNode"] = last_node
        return status

    def _count(self, entity_id: str) -> int:
        value = _finite_state(self._state(entity_id), "invalid_meshtastic_node_count")
        if value < 0 or not value.is_integer():
            raise ValueError("invalid_meshtastic_node_count")
        return int(value)

    def _optional_node_name(self, entity_id: str) -> str | None:
        """Returns a publishable name, or None when the optional lastNode must be omitted."""
        try:
            state = self._state(entity_id).get("state")
        except HTTPError as error:
            # A removed or renamed entity only drops the optional name; other HTTP failures still fail the panel.
            if error.code == 404:
                return None
            raise
        if not isinstance(state, str):
            return None
        normalized = " ".join(state.split())
        if (
            normalized.casefold() in _PLACEHOLDER_STATES
            or len(normalized) > _MAX_NODE_NAME_LENGTH
            or not normalized.isprintable()
        ):
            return None
        return normalized


class HomeAssistantMeshtasticClient:
    """Reads a fixed, private entity map and returns a public Meshtastic projection."""

    def __init__(self, base_url: str, token: str, entity_ids: Mapping[str, str], cache_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.entity_ids = dict(entity_ids)
        self.cache_seconds = max(cache_seconds, 15)
        self._cached_status: dict[str, object] | None = None
        self._cache_expires_at = 0.0

    def status(self) -> dict[str, object]:
        now = time.monotonic()
        if self._cached_status is not None and now < self._cache_expires_at:
            return self._cached_status

        values = {key: self._state(entity_id) for key, entity_id in self.entity_ids.items()}
        self._cached_status = {
            "status": "available" if values["gateway"] == "Connected" else "unavailable",
            "gateway": {
                "name": self._text(values["node_long_name"], maximum=128) or self._text(values["node_short_name"], maximum=32),
                "shortName": self._text(values["node_short_name"], maximum=32),
                "uptimeSeconds": self._integer(values["uptime_seconds"], minimum=0),
                "batteryPercent": self._number(values["battery_percent"], minimum=0, maximum=100),
                "voltage": self._number(values["voltage"], minimum=0),
            },
            "network": {
                "nodesOnline": self._integer(values["nodes_online"], minimum=0),
                "nodesTotal": self._integer(values["nodes_total"], minimum=0),
                "channelUtilizationPercent": self._number(values["channel_utilization_percent"], minimum=0, maximum=100),
                "airtimeTxPercent": self._number(values["airtime_tx_percent"], minimum=0, maximum=100),
            },
            "packets": {
                "rx": self._integer(values["packets_rx"], minimum=0),
                "tx": self._integer(values["packets_tx"], minimum=0),
                "rxBad": self._integer(values["packets_rx_bad"], minimum=0),
                "rxDuplicate": self._integer(values["packets_rx_duplicate"], minimum=0),
                "txRelayed": self._integer(values["packets_tx_relayed"], minimum=0),
                "txRelayCancelled": self._integer(values["packets_tx_relay_cancelled"], minimum=0),
            },
            "ratesPerMinute": {
                "rx": self._number(values["rx_per_minute"], minimum=0),
                "tx": self._number(values["tx_per_minute"], minimum=0),
                "rfErrors": self._number(values["rf_errors_per_minute"], minimum=0),
                "duplicates": self._number(values["duplicates_per_minute"], minimum=0),
                "relayCancelled": self._number(values["relay_cancelled_per_minute"], minimum=0),
            },
            "recentActivity": self._recent_activity(values),
            "refreshedAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        self._cache_expires_at = now + self.cache_seconds
        return self._cached_status

    def broadcast(self, message: str) -> None:
        body = json.dumps({"message": message}).encode()
        request = Request(
            f"{self.base_url}/api/services/script/meshtastic_public_broadcast",
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=MESHTASTIC_BROADCAST_TIMEOUT_SECONDS) as response:
            if response.status not in {200, 201}:
                raise RuntimeError("meshtastic_broadcast_failed")
        self._cache_expires_at = 0
        self._cached_status = None

    def _recent_activity(self, values: Mapping[str, object]) -> list[dict[str, str]]:
        activity: list[dict[str, str]] = []
        for index in range(1, 6):
            value = values[f"recent_activity_{index}"]
            if not isinstance(value, str):
                continue
            try:
                entry = json.loads(value)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            message = self._text(entry.get("message"), maximum=140)
            sender = self._text(entry.get("sender"), maximum=32)
            received_at = self._text(entry.get("receivedAt"), maximum=32)
            if message is None or sender is None or received_at is None:
                continue
            activity.append({"message": message, "sender": sender, "channel": "MediumFast", "receivedAt": received_at})
        return activity

    def _state(self, entity_id: str) -> object:
        payload = self._get_json(f"/api/states/{entity_id}")
        return payload.get("state")

    @staticmethod
    def _integer(value: object, minimum: int) -> int | None:
        try:
            number = int(str(value))
        except (TypeError, ValueError):
            return None
        return number if number >= minimum else None

    @staticmethod
    def _text(value: object, maximum: int) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value if value and value not in {"unknown", "unavailable"} and len(value) <= maximum else None

    @staticmethod
    def _number(value: object, minimum: float, maximum: float | None = None) -> float | None:
        try:
            number = float(str(value))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
            return None
        return round(number, 2)

    def _get_json(self, path: str) -> dict[str, object]:
        return _read_json(self.base_url, self.token, path, _REQUEST_TIMEOUT_SECONDS)
