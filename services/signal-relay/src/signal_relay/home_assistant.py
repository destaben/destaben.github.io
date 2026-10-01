from __future__ import annotations

from datetime import UTC, datetime
import json
import math
import re
import time
from typing import Mapping
from urllib.request import Request, urlopen


class HomeAssistantLabClient:
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
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.temperature_entity_id = temperature_entity_id
        self.humidity_entity_id = humidity_entity_id
        self.air_quality_entity_id = air_quality_entity_id
        self.cache_seconds = max(cache_seconds, 900)
        self._cached_status: dict[str, object] | None = None
        self._cache_expires_at = 0.0

    def status(self) -> dict[str, object]:
        now = time.monotonic()
        if self._cached_status is not None and now < self._cache_expires_at:
            return self._cached_status

        self._get_json("/api/")
        temperature = self._state_value(self.temperature_entity_id, "temperature", "°C")
        humidity = self._state_value(self.humidity_entity_id, "humidity", "%")
        air_quality = self._air_quality()
        refreshed_at = datetime.now(UTC).replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")
        self._cached_status = {
            "status": "available",
            "temperatureC": round(temperature),
            "humidityPercent": round(humidity / 5) * 5,
            "airQuality": air_quality,
            "refreshedAt": refreshed_at,
        }
        self._cache_expires_at = now + self.cache_seconds
        return self._cached_status

    def _state_value(self, entity_id: str, expected_device_class: str, expected_unit: str) -> float:
        payload = self._get_json(f"/api/states/{entity_id}")
        attributes = payload.get("attributes")
        if not isinstance(attributes, dict):
            raise ValueError("invalid_home_assistant_state")
        if attributes.get("device_class") != expected_device_class or attributes.get("unit_of_measurement") != expected_unit:
            raise ValueError("unexpected_home_assistant_unit")
        value = float(payload.get("state", ""))
        if not math.isfinite(value):
            raise ValueError("invalid_home_assistant_value")
        return value

    def _air_quality(self) -> str:
        payload = self._get_json(f"/api/states/{self.air_quality_entity_id}")
        attributes = payload.get("attributes")
        if not isinstance(attributes, dict):
            raise ValueError("invalid_home_assistant_state")
        device_class = attributes.get("device_class")
        unit = attributes.get("unit_of_measurement")
        value = float(payload.get("state", ""))
        if not math.isfinite(value):
            raise ValueError("invalid_home_assistant_value")
        if device_class == "pm25" and isinstance(unit, str) and unit.replace("μ", "µ") == "µg/m³":
            return "good" if value <= 12 else "regular" if value <= 35 else "bad"
        if device_class == "carbon_dioxide" and unit == "ppm":
            return "good" if value <= 800 else "regular" if value <= 1200 else "bad"
        raise ValueError("unsupported_air_quality_metric")

    def _get_json(self, path: str) -> dict[str, object]:
        request = Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
        if not isinstance(payload, dict):
            raise ValueError("invalid_home_assistant_response")
        return payload


class HomeAssistantMeshtasticClient:
    """Reads a fixed, private entity map and returns a public Meshtastic projection."""

    _NODE_FIELD = re.compile(r"^(sensor\.meshtastic_.+)_node_(long_name|short_name|snr|hops_away)$")

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
            "neighbors": self._neighbors(),
            "latestActivity": self._latest_activity(values),
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
        with urlopen(request, timeout=5) as response:
            if response.status not in {200, 201}:
                raise RuntimeError("meshtastic_broadcast_failed")

    def _latest_activity(self, values: Mapping[str, object]) -> dict[str, object] | None:
        activity_keys = ("last_message", "last_sender", "last_channel", "last_received")
        if not all(
            isinstance(values[key], str) and values[key] not in {"", "unknown", "unavailable"}
            for key in activity_keys
        ):
            return None
        hops = self._integer(values["last_sender_hops"], minimum=0) if values["last_sender_hops_available"] == "on" else None
        return {
            "message": values["last_message"],
            "sender": values["last_sender"],
            "channel": values["last_channel"],
            "receivedAt": values["last_received"],
            "senderHopsAway": hops,
        }

    def _neighbors(self) -> list[dict[str, object]]:
        local_entity_ids = {
            entity_id
            for key, entity_id in self.entity_ids.items()
            if key in {"node_long_name", "node_short_name"}
        }
        candidates: dict[str, dict[str, object]] = {}
        try:
            states = self._get_states()
        except (OSError, ValueError):
            return []
        for state in states:
            if not isinstance(state, dict):
                continue
            entity_id = state.get("entity_id")
            if not isinstance(entity_id, str) or entity_id in local_entity_ids:
                continue
            match = self._NODE_FIELD.fullmatch(entity_id)
            if match is None:
                continue
            candidates.setdefault(match.group(1), {})[match.group(2)] = state.get("state")
        for candidate in (candidates[key] for key in sorted(candidates)):
            name = self._text(candidate.get("long_name"), maximum=128) or self._text(candidate.get("short_name"), maximum=32)
            snr = self._number(candidate.get("snr"), minimum=-40, maximum=40)
            hops_away = self._integer(candidate.get("hops_away"), minimum=0)
            if name is not None and snr is not None and hops_away is not None:
                return [{
                    "name": name,
                    "shortName": self._text(candidate.get("short_name"), maximum=32),
                    "snr": snr,
                    "hopsAway": hops_away,
                }]
        return []

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
        request = Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
        if not isinstance(payload, dict):
            raise ValueError("invalid_home_assistant_response")
        return payload

    def _get_states(self) -> list[object]:
        request = Request(
            f"{self.base_url}/api/states",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
        if not isinstance(payload, list):
            raise ValueError("invalid_home_assistant_response")
        return payload