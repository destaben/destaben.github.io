from __future__ import annotations

from datetime import UTC, datetime
import json
import math
import time
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