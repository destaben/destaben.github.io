"""3D printer laboratory client: Moonraker state, model cache, and thumbnail, read only through the edge's nginx:8082.

The relay never speaks to Moonraker or to the printer host. Every request target is one of the fixed paths the
edge allows on its internal listener, and each one is built here from validated values. The public projection
keeps the filename private unless the operator opts in, and the model identifier is an opaque keyed hash.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import http.client
import json
import logging
import math
import os
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Callable, Iterator
from urllib.parse import quote, urlsplit

from .gcode_model import ModelRejected, ParsedModel, parse_gcode, started_layer_count

logger = logging.getLogger("uvicorn.error")

STATUS_TARGET = "/printer/objects/query?print_stats&virtual_sdcard"
_METADATA_PATH = "/server/files/metadata"
_GCODES_PATH = "/server/files/gcodes/"
# One poll serves every browser request for this long, so concurrent polls share a single upstream call.
_STATUS_CACHE_SECONDS = 5.0
_METADATA_CACHE_SECONDS = 300.0
# A failed download, thumbnail, or metadata read is not attempted again for this long.
_BACKOFF_SECONDS = 300.0
_CONNECT_TIMEOUT_SECONDS = 3.0
_JSON_READ_TIMEOUT_SECONDS = 10.0
_THUMBNAIL_READ_TIMEOUT_SECONDS = 10.0
# The edge throttles G-code downloads to one at a time; a stalled stream is abandoned after this much silence.
_DOWNLOAD_READ_TIMEOUT_SECONDS = 30.0
MAX_GCODE_BYTES = 150 * 1024 * 1024
_MAX_THUMBNAIL_BYTES = 512 * 1024
_MAX_JSON_BYTES = 256 * 1024
_MAX_FILENAME_LENGTH = 255
_READ_CHUNK_BYTES = 64 * 1024
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Disk keeps the newest parsed models; memory keeps the recent ones that the model route may serve.
_RETAINED_MODELS = 8
_RECENT_MODELS = 4
_RETAINED_THUMBNAILS = 2
_CACHED_METADATA_FILES = 16
_REMEMBERED_REJECTIONS = 64
_PRINT_STATES = {
    "standby": "idle",
    "printing": "printing",
    "paused": "paused",
    "complete": "complete",
    "cancelled": "cancelled",
    "error": "error",
}
_ACTIVE_STATES = frozenset({"printing", "paused"})
# The edge's allowlist for G-code and thumbnail names. Anything else is never requested.
# "+" is excluded on purpose: the edge accepts only a literal "+" in the metadata query, which Moonraker would
# decode as a space (the wrong file), and refuses "%2B". Such a job keeps its progress but gets no model.
_GCODE_NAME = re.compile(r"[-A-Za-z0-9_ .]+\.gcode")
_THUMBNAIL_PATH = re.compile(r"\.thumbs/[-A-Za-z0-9_+ .]+-[0-9]{2,4}x[0-9]{2,4}\.png")
_MODEL_ID = re.compile(r"[0-9a-f]{32}")

ModelKey = tuple[str, int, float]


class PrinterUnavailable(Exception):
    """Moonraker cannot be read right now. The public status reports the state as unavailable."""


def is_model_id(value: str) -> bool:
    return _MODEL_ID.fullmatch(value) is not None


def is_gcode_name(name: object) -> bool:
    return isinstance(name, str) and ".." not in name and _GCODE_NAME.fullmatch(name) is not None


def _is_thumbnail_path(path: object) -> bool:
    return isinstance(path, str) and ".." not in path and _THUMBNAIL_PATH.fullmatch(path) is not None


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _section(container: object, key: str) -> dict:
    value = container.get(key) if isinstance(container, dict) else None
    if not isinstance(value, dict):
        raise PrinterUnavailable(key)
    return value


def _count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _progress(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and 0 <= number <= 1 else None


def _close_quietly(response) -> None:
    try:
        response.close()
    except Exception:  # noqa: BLE001 - closing a finished response must never turn a handled outcome into a retry loop
        logger.debug("printer response could not be closed cleanly")


def _read_limited(response, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(_READ_CHUNK_BYTES)
        if not chunk:
            # http.client returns b"" on a premature close when Content-Length is set, instead of raising.
            if response.content_length is not None and total < response.content_length:
                raise PrinterUnavailable("truncated")
            return b"".join(chunks)
        total += len(chunk)
        if total > limit:
            raise PrinterUnavailable("response_too_large")
        chunks.append(chunk)


class _StreamFailed(Exception):
    """The body could not be read (network or framing fault). The file is not at fault, so this backs off, never rejects."""


def _stream_chunks(response, limit: int) -> Iterator[bytes]:
    """Yields the body in chunks and stops with a rejection once the cap is passed, so memory and bytes stay bounded."""
    total = 0
    while True:
        try:
            chunk = response.read(_READ_CHUNK_BYTES)
        except (OSError, http.client.HTTPException, ValueError) as error:
            # http.client raises ValueError for a malformed chunk size.
            raise _StreamFailed from error
        if not chunk:
            # A short body is a network fault, not a smaller file: publishing it would cache a wrong model.
            if response.content_length is not None and total < response.content_length:
                raise _StreamFailed
            return
        total += len(chunk)
        if total > limit:
            raise ModelRejected("too_large")
        yield chunk


class _HttpResponse:
    def __init__(self, connection: http.client.HTTPConnection, response: http.client.HTTPResponse) -> None:
        self._connection = connection
        self._response = response
        self.status = response.status
        declared = response.getheader("Content-Length")
        self.content_length = int(declared) if declared is not None and declared.isdigit() else None

    def read(self, size: int) -> bytes:
        return self._response.read(size)

    def close(self) -> None:
        self._connection.close()


class NginxTransport:
    """Plain HTTP GET to the edge's internal listener. The origin comes from configuration and is never taken from a request."""

    def __init__(self, base_url: str) -> None:
        parts = urlsplit(base_url)
        self._host = parts.hostname or ""
        self._port = parts.port or 80

    def get(self, target: str, read_timeout: float) -> _HttpResponse:
        connection = http.client.HTTPConnection(self._host, self._port, timeout=_CONNECT_TIMEOUT_SECONDS)
        try:
            connection.connect()
            connection.sock.settimeout(read_timeout)
            connection.request("GET", target, headers={"Accept": "*/*"})
            response = connection.getresponse()
        except BaseException:
            connection.close()
            raise
        return _HttpResponse(connection, response)


@dataclass(frozen=True)
class _Record:
    layer_offsets: tuple[int, ...]
    layer_zs: tuple[float, ...]


@dataclass(frozen=True)
class _Snapshot:
    state: str
    progress: float | None = None
    filename: str | None = None
    layer_current: int | None = None
    layer_total: int | None = None
    height_mm: float | None = None
    object_height_mm: float | None = None
    model_id: str | None = None
    thumbnail_path: str | None = None
    key: ModelKey | None = None
    updated_at: str = ""


def _model_key(filename: str | None, metadata: dict | None) -> ModelKey | None:
    """A model is identified by name, size, and modified time. Without the size and time there is no model."""
    if metadata is None or not is_gcode_name(filename):
        return None
    size = _count(metadata.get("size"))
    modified = _number(metadata.get("modified"))
    if size is None or modified is None:
        return None
    return (filename, size, modified)


def _thumbnail_path(metadata: dict | None) -> str | None:
    """The largest thumbnail whose path passes the allowlist; a path outside it is never returned."""
    if metadata is None or not isinstance(metadata.get("thumbnails"), list):
        return None
    best: str | None = None
    best_area = -1
    for entry in metadata["thumbnails"]:
        if not isinstance(entry, dict) or not _is_thumbnail_path(entry.get("relative_path")):
            continue
        area = (_count(entry.get("width")) or 0) * (_count(entry.get("height")) or 0)
        if best is None or area > best_area:
            best = entry["relative_path"]
            best_area = area
    return best


def _bounded(entries: OrderedDict, limit: int) -> None:
    while len(entries) > limit:
        entries.popitem(last=False)


class PrinterLabClient:
    """Thread-safe view of one printer. Blocking reads run in worker threads; the status poll is single-flight."""

    def __init__(
        self,
        transport,
        storage_dir: Path,
        *,
        show_filename: bool = False,
        clock: Callable[[], float] = time.monotonic,
        max_gcode_bytes: int = MAX_GCODE_BYTES,
    ) -> None:
        self._transport = transport
        self._root = Path(storage_dir) / "printer-lab"
        self._show_filename = show_filename
        self._clock = clock
        self._max_gcode_bytes = max_gcode_bytes
        # Guards the caches below. It is held across the status poll, so concurrent callers wait for one upstream call.
        self._lock = threading.Lock()
        # Held only by the one download that may run at a time; it is never waited on, only tried.
        self._download_lock = threading.Lock()
        self._thumbnail_lock = threading.Lock()
        self._snapshot: tuple[float, _Snapshot] | None = None
        self._metadata: OrderedDict[str, tuple[float, dict | None]] = OrderedDict()
        self._records: OrderedDict[str, _Record] = OrderedDict()
        self._thumbnails: OrderedDict[tuple[ModelKey, str], bytes] = OrderedDict()
        self._thumbnail_retry: OrderedDict[tuple[ModelKey, str], float] = OrderedDict()
        self._rejected: OrderedDict[ModelKey, str] = OrderedDict()
        self._download_retry_at = 0.0
        # Written by the poll and read without the lock by the worker, so the event loop never blocks on it.
        self._pending: ModelKey | None = None
        self._salt: bytes | None = None
        self._salt_lock = threading.Lock()

    # Public projection

    def status(self) -> dict[str, object]:
        snapshot = self._current_snapshot()
        body: dict[str, object] = {
            "state": snapshot.state,
            "progress": snapshot.progress,
            "layer": {"current": snapshot.layer_current, "total": snapshot.layer_total},
            "heightMm": snapshot.height_mm,
            "objectHeightMm": snapshot.object_height_mm,
            "modelId": snapshot.model_id,
            "thumbnail": snapshot.thumbnail_path is not None,
            "updatedAt": snapshot.updated_at,
        }
        if self._show_filename:
            body["filename"] = snapshot.filename
        return body

    def model(self, model_id: str) -> dict | None:
        """The drawable model for a recently seen job. Unknown or evicted IDs return None."""
        if not is_model_id(model_id):
            return None
        with self._lock:
            if model_id not in self._records:
                return None
        try:
            data = json.loads(self._model_path(model_id).read_bytes())
        except (OSError, ValueError):
            return None
        model = data.get("model") if isinstance(data, dict) else None
        return model if isinstance(model, dict) else None

    def thumbnail(self) -> bytes | None:
        snapshot = self._current_snapshot()
        if snapshot.key is None or snapshot.thumbnail_path is None:
            return None
        cache_key = (snapshot.key, snapshot.thumbnail_path)
        # One thumbnail read at a time, so a burst of requests for the same job shares the first read.
        with self._thumbnail_lock:
            with self._lock:
                cached = self._thumbnails.get(cache_key)
                if cached is not None:
                    self._thumbnails.move_to_end(cache_key)
                    return cached
                retry_at = self._thumbnail_retry.get(cache_key)
                if retry_at is not None and self._clock() < retry_at:
                    return None
            body = self._download_thumbnail(snapshot.thumbnail_path)
            with self._lock:
                if body is None:
                    self._thumbnail_retry[cache_key] = self._clock() + _BACKOFF_SECONDS
                    _bounded(self._thumbnail_retry, _REMEMBERED_REJECTIONS)
                    return None
                self._thumbnails[cache_key] = body
                self._thumbnails.move_to_end(cache_key)
                _bounded(self._thumbnails, _RETAINED_THUMBNAILS)
                return body

    # Worker

    def take_pending_model(self) -> ModelKey | None:
        """The job whose model should be parsed in the background, if any. Read without the lock on purpose."""
        key, self._pending = self._pending, None
        return key

    def prepare_model(self, key: ModelKey) -> None:
        """Downloads and parses one G-code file, at most once per job. Expected failures are logged, never raised."""
        if not is_gcode_name(key[0]):
            return
        with self._lock:
            if key in self._rejected or self._clock() < self._download_retry_at:
                return
        try:
            model_id = self._model_id(key)
            with self._lock:
                if model_id in self._records:
                    return
            if self._model_path(model_id).exists():
                return
        except OSError:
            logger.warning("printer model cache is unavailable")
            return
        if not self._download_lock.acquire(blocking=False):
            return
        try:
            self._download_and_store(key, model_id)
        finally:
            self._download_lock.release()

    # Status

    def _current_snapshot(self) -> _Snapshot:
        with self._lock:
            now = self._clock()
            if self._snapshot is not None and now < self._snapshot[0]:
                return self._snapshot[1]
            snapshot = self._poll(now)
            self._snapshot = (now + _STATUS_CACHE_SECONDS, snapshot)
            return snapshot

    def _poll(self, now: float) -> _Snapshot:
        try:
            status = _section(_section(self._fetch_json(STATUS_TARGET, _JSON_READ_TIMEOUT_SECONDS), "result"), "status")
            print_stats = _section(status, "print_stats")
            sdcard = _section(status, "virtual_sdcard")
        except PrinterUnavailable:
            return _Snapshot(state="unavailable", updated_at=_now())
        raw_state = print_stats.get("state")
        state = _PRINT_STATES.get(raw_state) if isinstance(raw_state, str) else None
        if state is None:
            return _Snapshot(state="unavailable", updated_at=_now())
        if state == "idle":
            return _Snapshot(state="idle", updated_at=_now())

        filename = print_stats.get("filename")
        if not isinstance(filename, str) or len(filename) > _MAX_FILENAME_LENGTH:
            filename = None
        position = _count(sdcard.get("file_position"))
        info = print_stats.get("info") if isinstance(print_stats.get("info"), dict) else {}
        info_current = _count(info.get("current_layer"))
        info_total = _count(info.get("total_layer"))
        metadata = self._metadata_for(filename, now) if is_gcode_name(filename) else None
        key = _model_key(filename, metadata)

        model_id: str | None = None
        record: _Record | None = None
        if key is not None:
            try:
                model_id, record = self._record_for(key)
            except OSError:
                logger.warning("printer model cache is unavailable")
            if record is None and state in _ACTIVE_STATES and key not in self._rejected and now >= self._download_retry_at:
                self._pending = key

        layer_current = info_current or None
        layer_total = info_total
        height_mm = None
        if record is not None:
            layer_total = len(record.layer_offsets)
            if position is not None:
                layer_current = started_layer_count(record.layer_offsets, position) or None
            if layer_current is not None and layer_current <= len(record.layer_zs):
                height_mm = record.layer_zs[layer_current - 1]
        object_height = _number(metadata.get("object_height")) if metadata is not None else None
        return _Snapshot(
            state=state,
            progress=_progress(sdcard.get("progress")),
            filename=filename,
            layer_current=layer_current,
            layer_total=layer_total,
            height_mm=height_mm,
            object_height_mm=object_height if object_height is not None and object_height >= 0 else None,
            model_id=model_id if record is not None else None,
            thumbnail_path=_thumbnail_path(metadata),
            key=key,
            updated_at=_now(),
        )

    def _metadata_for(self, filename: str, now: float) -> dict | None:
        cached = self._metadata.get(filename)
        if cached is not None and now < cached[0]:
            return cached[1]
        try:
            result = _section(self._fetch_json(f"{_METADATA_PATH}?filename={quote(filename, safe='-_.')}", _JSON_READ_TIMEOUT_SECONDS), "result")
        except PrinterUnavailable:
            result = None
            lifetime = _BACKOFF_SECONDS
        else:
            lifetime = _METADATA_CACHE_SECONDS
        self._metadata[filename] = (now + lifetime, result)
        self._metadata.move_to_end(filename)
        _bounded(self._metadata, _CACHED_METADATA_FILES)
        return result

    def _fetch_json(self, target: str, read_timeout: float) -> dict:
        try:
            response = self._transport.get(target, read_timeout)
        except (OSError, http.client.HTTPException) as error:
            raise PrinterUnavailable(target) from error
        try:
            if response.status != 200:
                raise PrinterUnavailable("http_status")
            body = _read_limited(response, _MAX_JSON_BYTES)
        except (OSError, http.client.HTTPException) as error:
            raise PrinterUnavailable(target) from error
        finally:
            response.close()
        try:
            payload = json.loads(body)
        except (ValueError, RecursionError) as error:
            raise PrinterUnavailable("malformed_json") from error
        if not isinstance(payload, dict) or "error" in payload:
            raise PrinterUnavailable("moonraker_error")
        return payload

    # Models

    def _record_for(self, key: ModelKey) -> tuple[str, _Record | None]:
        model_id = self._model_id(key)
        record = self._records.get(model_id)
        if record is not None:
            self._records.move_to_end(model_id)
            return model_id, record
        record = self._read_record(model_id)
        if record is not None:
            self._remember(model_id, record)
        return model_id, record

    def _remember(self, model_id: str, record: _Record) -> None:
        self._records[model_id] = record
        self._records.move_to_end(model_id)
        _bounded(self._records, _RECENT_MODELS)

    def _download_and_store(self, key: ModelKey, model_id: str) -> None:
        # Arm the backoff before touching the printer host and clear it only on success or a final rejection. Any
        # other way out of this method, including an exception nobody anticipated, then cannot cause a new
        # download on the next status poll.
        with self._lock:
            self._download_retry_at = self._clock() + _BACKOFF_SECONDS
        name = key[0]
        try:
            response = self._transport.get(_GCODES_PATH + quote(name, safe="-_.+"), _DOWNLOAD_READ_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001 - whatever the transport raises, the printer host must not be hit again before the backoff
            self._back_off("transport_error")
            return
        try:
            if response.status == 404:
                self._reject(key, "not_found")
                return
            if response.status != 200:
                self._back_off("http_status")
                return
            if response.content_length is not None and response.content_length > self._max_gcode_bytes:
                raise ModelRejected("too_large")
            parsed = parse_gcode(_stream_chunks(response, self._max_gcode_bytes))
        except ModelRejected as error:
            self._reject(key, str(error))
            return
        except _StreamFailed:
            self._back_off("stream_error")
            return
        except Exception:  # noqa: BLE001 - a file the parser cannot handle must never be fetched again from the printer host
            self._reject(key, "unparseable")
            return
        finally:
            _close_quietly(response)
        self._store(model_id, parsed)

    def _store(self, model_id: str, parsed: ParsedModel) -> None:
        try:
            self._write_model(model_id, parsed)
        except Exception:  # noqa: BLE001 - without a disk copy the model would be downloaded again on every poll
            logger.warning("printer model could not be stored")
            self._back_off("store_error")
            return
        with self._lock:
            self._remember(model_id, _Record(parsed.layer_offsets, parsed.layer_zs))
            self._download_retry_at = 0.0

    def _write_model(self, model_id: str, parsed: ParsedModel) -> None:
        directory = self._root / "models"
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f"{model_id}.tmp"
        body = json.dumps(
            {"offsets": list(parsed.layer_offsets), "zs": list(parsed.layer_zs), "model": parsed.payload},
            separators=(",", ":"),
        )
        temporary.write_text(body, encoding="utf-8")
        os.replace(temporary, self._model_path(model_id))
        files = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
        for stale in files[_RETAINED_MODELS:]:
            stale.unlink(missing_ok=True)

    def _read_record(self, model_id: str) -> _Record | None:
        path = self._model_path(model_id)
        try:
            data = json.loads(path.read_bytes())
        except FileNotFoundError:
            return None
        except ValueError:
            data = None
        offsets = data.get("offsets") if isinstance(data, dict) else None
        zs = data.get("zs") if isinstance(data, dict) else None
        if not (
            isinstance(offsets, list)
            and isinstance(zs, list)
            and len(offsets) == len(zs)
            and all(_count(offset) is not None for offset in offsets)
            and all(_number(z) is not None for z in zs)
        ):
            # A corrupt entry is removed, so the next attempt parses the file again instead of trusting it.
            logger.warning("printer model cache entry is unreadable")
            path.unlink(missing_ok=True)
            return None
        return _Record(tuple(offsets), tuple(float(z) for z in zs))

    def _model_path(self, model_id: str) -> Path:
        return self._root / "models" / f"{model_id}.json"

    def _model_id(self, key: ModelKey) -> str:
        name, size, modified = key
        material = f"{name}\x00{size}\x00{modified!r}".encode("utf-8")
        return hmac.new(self._load_salt(), material, hashlib.sha256).hexdigest()[:32]

    def _load_salt(self) -> bytes:
        """A random key kept in the relay's storage, so identifiers are stable across restarts and not reversible."""
        # Serialized, so the poll and the worker never see a salt file that another thread is still writing.
        with self._salt_lock:
            if self._salt is None:
                self._root.mkdir(parents=True, exist_ok=True)
                path = self._root / "salt"
                try:
                    salt = path.read_bytes()
                except FileNotFoundError:
                    salt = b""
                if len(salt) != 32:
                    # A missing or truncated salt (for example after a crash while it was written) is replaced atomically.
                    salt = secrets.token_bytes(32)
                    temporary = self._root / "salt.tmp"
                    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(salt)
                    os.replace(temporary, path)
                self._salt = salt
            return self._salt

    def _reject(self, key: ModelKey, reason: str) -> None:
        logger.info("printer model was not published: %s", reason)
        with self._lock:
            self._rejected[key] = reason
            _bounded(self._rejected, _REMEMBERED_REJECTIONS)
            self._download_retry_at = 0.0  # the file itself is now remembered as refused, so the next job is not delayed

    def _back_off(self, reason: str) -> None:
        logger.warning("printer model download backed off: %s", reason)
        with self._lock:
            self._download_retry_at = self._clock() + _BACKOFF_SECONDS

    def _download_thumbnail(self, path: str) -> bytes | None:
        try:
            response = self._transport.get(_GCODES_PATH + quote(path, safe="/-_.+"), _THUMBNAIL_READ_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001 - the caller records a retry time for any failure
            return None
        try:
            if response.status != 200:
                return None
            if response.content_length is not None and response.content_length > _MAX_THUMBNAIL_BYTES:
                return None
            body = _read_limited(response, _MAX_THUMBNAIL_BYTES)
        except Exception:  # noqa: BLE001
            return None
        finally:
            _close_quietly(response)
        return body if body.startswith(_PNG_SIGNATURE) else None


def build_printer_client(base_url: str, storage_dir: Path, *, show_filename: bool) -> PrinterLabClient:
    return PrinterLabClient(NginxTransport(base_url), storage_dir, show_filename=show_filename)


class PrinterModelWorker:
    """Runs at most one model download and parse at a time, as an asyncio task that calls the blocking client in a thread."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self, client: PrinterLabClient) -> asyncio.Task | None:
        if self._task is not None and not self._task.done():
            return None
        key = client.take_pending_model()
        if key is None:
            return None
        self._task = asyncio.get_running_loop().create_task(asyncio.to_thread(client.prepare_model, key))
        self._task.add_done_callback(_report_failure)
        return self._task

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()


def _report_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.error("printer model worker failed", exc_info=task.exception())
