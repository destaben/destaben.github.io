"""Pure G-code parser that turns a streamed print file into a bounded layer model for the laboratory viewer.

The parser reads the file as byte chunks and never holds more than one line of it. It records the byte offset of
every ``;LAYER_CHANGE`` line, so a Moonraker ``file_position`` can be mapped to a layer, and it draws only the
extrusion of outer walls, as quantized polylines simplified with Douglas-Peucker.
"""

from __future__ import annotations

from array import array
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
import json
import math
from typing import Iterable, Sequence

# Caps. A file that breaks one of them is rejected whole; it is never published partially. A cap is only
# exceeded after the tolerance has been raised as far as _MAX_TOLERANCE, which is the one place a model is dropped.
MAX_POINTS = 150_000
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_LAYERS = 5_000
MAX_LINE_BYTES = 16 * 1024
# Douglas-Peucker tolerance in tenths of a millimetre: 2.0 is 0.2 mm. It doubles while a cap is exceeded.
_INITIAL_TOLERANCE = 2.0
_MAX_TOLERANCE = 32.0
_UNITS_PER_MM = 10
# The ;TYPE: names that mark an outer wall. "External perimeter" is the PrusaSlicer spelling of the same feature.
OUTER_WALL_TYPES = frozenset({"Outer wall", "External perimeter"})
_LAYER_CHANGE = ";LAYER_CHANGE"


# No printer reaches 100 m. Anything beyond is a corrupt or hostile file, and it would overflow the packed int array.
_MAX_COORDINATE_MM = 100_000.0


def _units(millimetres: float) -> int:
    if not math.isfinite(millimetres) or abs(millimetres) > _MAX_COORDINATE_MM:
        raise ModelRejected("out_of_range")
    return round(millimetres * _UNITS_PER_MM)


class ModelRejected(Exception):
    """A G-code file that cannot be published within the caps. The message is a fixed reason code, never file content."""


@dataclass(frozen=True)
class ParsedModel:
    layer_offsets: tuple[int, ...]
    layer_zs: tuple[float, ...]
    payload: dict[str, object]


def started_layer_count(layer_offsets: Sequence[int], file_position: int) -> int:
    """Number of layers whose ``;LAYER_CHANGE`` line starts at or before the printed file position."""
    return bisect_right(layer_offsets, file_position)


def parse_gcode(chunks: Iterable[bytes]) -> ParsedModel:
    builder = _Builder()
    offset = 0
    for raw_line in _lines(chunks):
        builder.consume(raw_line, offset)
        offset += len(raw_line)
    builder.finish()
    return builder.model()


def _lines(chunks: Iterable[bytes]):
    """Yields whole physical lines (terminator included) without holding more than one partial line."""
    pending = bytearray()
    for chunk in chunks:
        pending.extend(chunk)
        start = 0
        while (end := pending.find(b"\n", start)) >= 0:
            if end + 1 - start > MAX_LINE_BYTES:
                raise ModelRejected("line_too_long")
            yield bytes(pending[start:end + 1])
            start = end + 1
        del pending[:start]
        if len(pending) > MAX_LINE_BYTES:
            raise ModelRejected("line_too_long")
    if pending:
        yield bytes(pending)


def _number(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _integer(text: str) -> int | None:
    return int(text) if text.isdigit() else None


def _parameters(words: Iterable[str]) -> dict[str, float]:
    parameters: dict[str, float] = {}
    for word in words:
        value = _number(word[1:])
        if value is not None:
            parameters.setdefault(word[0].upper(), value)
    return parameters


class _Layer:
    __slots__ = ("offset", "z", "paths")

    def __init__(self, offset: int, z: float | None) -> None:
        self.offset = offset
        self.z = z
        self.paths: list[array] = []


class _Builder:
    def __init__(self) -> None:
        self.tolerance = _INITIAL_TOLERANCE
        self.layers: list[_Layer] = []
        self.heights: Counter[float] = Counter()
        self.points = 0
        # Machine state. A coordinate is None while its value is unknown, so no segment is drawn from it.
        self.x: float | None = None
        self.y: float | None = None
        self.z: float | None = None
        self.e = 0.0
        self.relative_xyz = False
        self.relative_e = False
        self.outer = False
        self.path: list[tuple[int, int]] | None = None

    def consume(self, raw_line: bytes, offset: int) -> None:
        text = raw_line.decode("ascii", "replace").strip()
        if not text:
            return
        if text.startswith(";"):
            self._comment(text, offset)
            return
        code = text.split(";", 1)[0].strip()
        if code:
            self._command(code)

    def finish(self) -> None:
        self._close_path()
        self._fit_points()

    def model(self) -> ParsedModel:
        payload = self.payload()
        while len(json.dumps(payload, separators=(",", ":"))) > MAX_JSON_BYTES:
            self._coarsen("model_too_large")
            payload = self.payload()
        zs = self._zs()
        return ParsedModel(
            layer_offsets=tuple(layer.offset for layer in self.layers),
            layer_zs=tuple(zs),
            payload=payload,
        )

    def payload(self) -> dict[str, object]:
        zs = self._zs()
        layers = [
            {"z": z, "paths": [list(path) for path in layer.paths]}
            for layer, z in zip(self.layers, zs)
        ]
        return {
            "layerHeight": self._layer_height(zs),
            "layerCount": len(layers),
            "bbox": _bounding_box(self.layers),
            "layers": layers,
        }

    # Comments and markers

    def _comment(self, text: str, offset: int) -> None:
        if text == _LAYER_CHANGE:
            self._start_layer(offset)
        elif text.startswith(";Z:"):
            z = _number(text[3:])
            if z is not None:
                self.z = z
                if self.layers:
                    self.layers[-1].z = z
        elif text.startswith(";HEIGHT:"):
            height = _number(text[8:])
            if height is not None and height > 0:
                self.heights[round(height, 3)] += 1
        elif text.startswith(";TYPE:"):
            outer = text[6:].strip() in OUTER_WALL_TYPES
            if not outer:
                self._close_path()
            self.outer = outer

    def _start_layer(self, offset: int) -> None:
        self._close_path()
        self._fit_points()
        if len(self.layers) + 1 > MAX_LAYERS:
            raise ModelRejected("too_many_layers")
        self.layers.append(_Layer(offset, self.z))

    # Commands

    def _command(self, code: str) -> None:
        words = code.split()
        if len(words) > 1 and words[0][:1] in ("N", "n") and words[0][1:].isdigit():
            words = words[1:]
        if not words:
            return
        word = words[0].upper()
        number = _integer(word[1:])
        if number is None:
            return
        parameters = _parameters(words[1:])
        if word[0] == "G":
            self._g_command(number, parameters)
        elif word[0] == "M":
            if number == 82:
                self.relative_e = False
            elif number == 83:
                self.relative_e = True

    def _g_command(self, number: int, parameters: dict[str, float]) -> None:
        if number in (0, 1, 2, 3):
            self._move(parameters)
        elif number == 28:
            self._home(parameters)
        elif number == 90:
            self.relative_xyz = False
        elif number == 91:
            self.relative_xyz = True
        elif number == 92:
            self._set_position(parameters)

    def _move(self, parameters: dict[str, float]) -> None:
        start_x, start_y = self.x, self.y
        end_x = self._target("X", parameters, self.x)
        end_y = self._target("Y", parameters, self.y)
        end_z = self._target("Z", parameters, self.z)
        extruding = False
        if "E" in parameters:
            value = parameters["E"]
            if self.relative_e:
                extruding = value > 0
            else:
                extruding = value > self.e
                self.e = value
        positions_known = all(value is not None for value in (start_x, start_y, end_x, end_y))
        if self.outer and extruding and positions_known:
            self._draw(start_x, start_y, end_x, end_y)
        else:
            self._close_path()
        self.x, self.y, self.z = end_x, end_y, end_z

    def _target(self, axis: str, parameters: dict[str, float], current: float | None) -> float | None:
        if axis not in parameters:
            return current
        value = parameters[axis]
        if not self.relative_xyz:
            return value
        return None if current is None else current + value

    def _home(self, parameters: dict[str, float]) -> None:
        axes = [axis for axis in "XYZ" if axis in parameters] or ["X", "Y", "Z"]
        self._close_path()
        if "X" in axes:
            self.x = None
        if "Y" in axes:
            self.y = None
        if "Z" in axes:
            self.z = None

    def _set_position(self, parameters: dict[str, float]) -> None:
        if any(axis in parameters for axis in "XYZ"):
            self._close_path()
        if "X" in parameters:
            self.x = parameters["X"]
        if "Y" in parameters:
            self.y = parameters["Y"]
        if "Z" in parameters:
            self.z = parameters["Z"]
        if "E" in parameters:
            self.e = parameters["E"]

    # Polylines

    def _draw(self, start_x: float, start_y: float, end_x: float, end_y: float) -> None:
        start = (_units(start_x), _units(start_y))
        end = (_units(end_x), _units(end_y))
        if self.path is None or self.path[-1] != start:
            self._close_path()
            self.path = [start]
        if self.path[-1] != end:
            self.path.append(end)

    def _close_path(self) -> None:
        path = self.path
        self.path = None
        if path is None or not self.layers:
            return
        kept = _simplify(path, self.tolerance)
        if len(kept) < 2:
            return
        self.layers[-1].paths.append(_pack(kept))
        self.points += len(kept)

    def _fit_points(self) -> None:
        while self.points > MAX_POINTS:
            self._coarsen("too_many_points")

    def _coarsen(self, reason: str) -> None:
        if self.tolerance * 2 > _MAX_TOLERANCE:
            raise ModelRejected(reason)
        self.tolerance *= 2
        self.points = 0
        for layer in self.layers:
            layer.paths = [_pack(_simplify(_unpack(path), self.tolerance)) for path in layer.paths]
            self.points += sum(len(path) // 2 for path in layer.paths)

    # Derived values

    def _zs(self) -> list[float]:
        zs: list[float] = []
        last = 0.0
        for layer in self.layers:
            if layer.z is not None:
                last = layer.z
            zs.append(round(last, 3))
        return zs

    def _layer_height(self, zs: list[float]) -> float | None:
        if self.heights:
            return self.heights.most_common(1)[0][0]
        steps = sorted(round(later - earlier, 3) for earlier, later in zip(zs, zs[1:]) if later > earlier)
        return steps[len(steps) // 2] if steps else None


def _pack(points: Sequence[tuple[int, int]]) -> array:
    packed = array("i")
    for x, y in points:
        packed.append(x)
        packed.append(y)
    return packed


def _unpack(packed: array) -> list[tuple[int, int]]:
    return list(zip(packed[0::2], packed[1::2]))


def _simplify(points: Sequence[tuple[int, int]], tolerance: float) -> list[tuple[int, int]]:
    """Iterative Douglas-Peucker. The first and last points are always kept, so a polyline keeps its ends."""
    count = len(points)
    if count <= 2:
        return list(points)
    keep = [False] * count
    keep[0] = keep[-1] = True
    stack = [(0, count - 1)]
    while stack:
        first, last = stack.pop()
        ax, ay = points[first]
        bx, by = points[last]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        worst_distance = -1.0
        worst_index = -1
        for index in range(first + 1, last):
            px, py = points[index]
            if length == 0:
                distance = math.hypot(px - ax, py - ay)
            else:
                distance = abs(dx * (py - ay) - dy * (px - ax)) / length
            if distance > worst_distance:
                worst_distance = distance
                worst_index = index
        if worst_distance > tolerance:
            keep[worst_index] = True
            stack.append((first, worst_index))
            stack.append((worst_index, last))
    return [point for point, kept in zip(points, keep) if kept]


def _bounding_box(layers: Sequence[_Layer]) -> dict[str, float] | None:
    minimum_x = minimum_y = None
    maximum_x = maximum_y = None
    for layer in layers:
        for path in layer.paths:
            for x, y in _unpack(path):
                minimum_x = x if minimum_x is None or x < minimum_x else minimum_x
                maximum_x = x if maximum_x is None or x > maximum_x else maximum_x
                minimum_y = y if minimum_y is None or y < minimum_y else minimum_y
                maximum_y = y if maximum_y is None or y > maximum_y else maximum_y
    if minimum_x is None:
        return None
    return {
        "minX": round(minimum_x / _UNITS_PER_MM, 1),
        "minY": round(minimum_y / _UNITS_PER_MM, 1),
        "maxX": round(maximum_x / _UNITS_PER_MM, 1),
        "maxY": round(maximum_y / _UNITS_PER_MM, 1),
    }
