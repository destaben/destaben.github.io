from __future__ import annotations

import json
import math
from urllib.parse import urlencode
from urllib.request import urlopen


class PrometheusLabClient:
    """Read a small, fixed set of container signals for the public lab."""

    QUERIES = {
        "cpu": "sum by (name) (rate(container_cpu_usage_seconds_total{image!=\"\"}[2m]))",
        "memory": "sum by (name) (container_memory_working_set_bytes{image!=\"\"})",
    }

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def query_range(self, metric: str, start: int, end: int, step: int) -> dict[str, object]:
        if metric not in self.QUERIES:
            raise ValueError("unknown_metric")
        query = urlencode({"query": self.QUERIES[metric], "start": start, "end": end, "step": step})
        with urlopen(f"{self.base_url}/api/v1/query_range?{query}", timeout=5) as response:
            payload = json.load(response)
        if payload.get("status") != "success" or payload.get("data", {}).get("resultType") != "matrix":
            raise RuntimeError("prometheus_unavailable")

        series = []
        for result in payload["data"]["result"]:
            name = self._container_name(result.get("metric", {}))
            values = self._values(result.get("values", []))
            if name and values:
                series.append({"name": name, "values": values})
        return {"metric": metric, "start": start, "end": end, "series": sorted(series, key=lambda item: item["name"])}

    @staticmethod
    def _container_name(labels: dict[str, str]) -> str:
        name = labels.get("name") or labels.get("container") or ""
        return name.rsplit("/", 1)[-1].lstrip("/")

    @staticmethod
    def _values(values: list[list[str | float]]) -> list[list[float]]:
        parsed = []
        for timestamp, value in values:
            number = float(value)
            if math.isfinite(number):
                parsed.append([float(timestamp), number])
        return parsed