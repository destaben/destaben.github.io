import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import re
import threading
import time
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from signal_relay import printer as printer_module
from signal_relay.app import create_app
from signal_relay.config import Settings
from signal_relay.printer import NginxTransport, PrinterLabClient, PrinterModelWorker

STATUS_TARGET = "/printer/objects/query?print_stats&virtual_sdcard"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
GCODE_NAME = re.compile(r"[-A-Za-z0-9_+ .]+\.gcode")
THUMBNAIL_NAME = re.compile(r"\.thumbs/[-A-Za-z0-9_+ .]+-[0-9]{2,4}x[0-9]{2,4}\.png")
# The edge matches the raw metadata query: only %20 and a literal "+" are accepted, and Moonraker would read a literal "+" as a space.
EDGE_METADATA_ARGUMENT = re.compile(r"filename=(?:[-A-Za-z0-9_]|%20|\.(?!\.))+\.gcode")
MODEL_ID = re.compile(r"[0-9a-f]{32}")

PRINT_GCODE = (
    ";LAYER_CHANGE\n;Z:0.2\n;HEIGHT:0.2\nG90\nG1 X0 Y0 Z0.2\n"
    ";TYPE:Outer wall\nG1 X10 Y0 E1\nG1 X10 Y10 E2\n"
    ";LAYER_CHANGE\n;Z:0.4\n;HEIGHT:0.2\nG1 X0 Y0 Z0.4\n"
    ";TYPE:Outer wall\nG1 X10 Y0 E3\n"
)
SECOND_LAYER_OFFSET = PRINT_GCODE.encode().rindex(b";LAYER_CHANGE")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _Response:
    def __init__(self, status: int, body: bytes = b"", content_length: int | None = None) -> None:
        self.status = status
        self.content_length = len(body) if content_length is None else content_length
        self._body = body
        self._offset = 0
        self.bytes_read = 0
        self.closed = False
        self.close_error: Exception | None = None

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error

    def read(self, size: int) -> bytes:
        chunk = self._body[self._offset:self._offset + size]
        self._offset += len(chunk)
        self.bytes_read += len(chunk)
        return chunk


def _raising(error: Exception):
    def read(size: int) -> bytes:
        raise error

    return read


class FakeMoonraker:
    """The nginx:8082 boundary. It records every target so tests can check the allowlist and the query string."""

    def __init__(self) -> None:
        self.status: dict | None = status_payload()
        self.raw_status: bytes | None = None
        self.unreachable = False
        self.metadata: dict[str, dict] = {}
        self.thumbnails: dict[str, bytes] = {}
        self.thumbnail_error = False
        self.thumbnail_gate: threading.Event | None = None
        self.thumbnail_entered = threading.Event()
        self.gcode: dict[str, bytes] = {}
        self.gcode_status = 200
        self.gcode_content_length: int | None | str = "body"
        self.gcode_gate: threading.Event | None = None
        self.gcode_entered = threading.Event()
        self.status_gate: threading.Event | None = None
        self.entered = threading.Event()
        self.targets: list[str] = []
        self.timeouts: list[tuple[str, float]] = []
        self.gcode_responses: list[_Response] = []
        self.targets_failed = 0
        self.gcode_get_error: Exception | None = None
        self.gcode_read_error: Exception | None = None
        self.gcode_close_error: Exception | None = None
        self.thumbnail_get_error: Exception | None = None

    def get(self, target: str, read_timeout: float) -> _Response:
        self.targets.append(target)
        self.timeouts.append((target, read_timeout))
        if self.unreachable:
            raise OSError("unreachable")
        path = target.split("?", 1)[0]
        if target == STATUS_TARGET:
            self.entered.set()
            if self.status_gate is not None:
                self.status_gate.wait(5)
            if self.raw_status is not None:
                return _Response(200, self.raw_status)
            if self.status is None:
                return _Response(500, b'{"error":"klippy not ready"}')
            return _Response(200, json.dumps(self.status).encode())
        if path == "/server/files/metadata":
            name = unquote(target.split("filename=", 1)[1])
            if name not in self.metadata:
                return _Response(404)
            return _Response(200, json.dumps({"result": self.metadata[name]}).encode())
        prefix = "/server/files/gcodes/"
        if path.startswith(prefix + ".thumbs/"):
            self.thumbnail_entered.set()
            if self.thumbnail_gate is not None:
                self.thumbnail_gate.wait(5)
            if self.thumbnail_get_error is not None:
                raise self.thumbnail_get_error
            relative = path[len(prefix):]
            if self.thumbnail_error or relative not in self.thumbnails:
                return _Response(404)
            return _Response(200, self.thumbnails[relative])
        if path.startswith(prefix) and path.endswith(".gcode"):
            self.gcode_entered.set()
            if self.gcode_gate is not None:
                self.gcode_gate.wait(5)
            if self.gcode_get_error is not None:
                self.targets_failed += 1
                raise self.gcode_get_error
            name = unquote(path[len(prefix):])
            if self.gcode_status != 200:
                response = _Response(self.gcode_status)
            elif name not in self.gcode:
                response = _Response(404)
            else:
                body = self.gcode[name]
                length = None if self.gcode_content_length is None else (
                    len(body) if self.gcode_content_length == "body" else self.gcode_content_length
                )
                response = _Response(200, body, length)
            if self.gcode_read_error is not None:
                response.read = _raising(self.gcode_read_error)
            response.close_error = self.gcode_close_error
            self.gcode_responses.append(response)
            return response
        return _Response(404)

    def count(self, prefix: str) -> int:
        return sum(1 for target in self.targets if target.startswith(prefix))


def status_payload(state: str = "printing", filename: str | None = "benchy.gcode", position: int | None = None,
                   progress: float | None = 0.5, info: dict | None = None) -> dict:
    return {"result": {"status": {
        "print_stats": {"state": state, "filename": filename, "info": info},
        "virtual_sdcard": {"progress": progress, "file_position": position, "is_active": True},
    }}}


def metadata_payload(size: int, object_height: float = 1.0) -> dict:
    return {
        "size": size,
        "modified": 1_700_000_000.25,
        "object_height": object_height,
        "layer_height": 0.2,
        "thumbnails": [
            {"width": 32, "height": 32, "size": 100, "relative_path": ".thumbs/benchy-32x32.png"},
            {"width": 400, "height": 300, "size": 900, "relative_path": ".thumbs/benchy-400x300.png"},
        ],
    }


def printing_fake(position: int | None = None, filename: str = "benchy.gcode", gcode: str = PRINT_GCODE,
                  state: str = "printing") -> FakeMoonraker:
    fake = FakeMoonraker()
    fake.status = status_payload(state, filename, position)
    fake.metadata[filename] = metadata_payload(len(gcode.encode()))
    fake.gcode[filename] = gcode.encode()
    fake.thumbnails[".thumbs/benchy-400x300.png"] = PNG
    fake.thumbnails[".thumbs/benchy-32x32.png"] = PNG
    return fake


def make_client(storage, fake: FakeMoonraker, clock: FakeClock | None = None, **options) -> PrinterLabClient:
    return PrinterLabClient(fake, storage, clock=clock or FakeClock(), **options)


def settings_for(tmp_path, *, enabled: bool = True, show_filename: bool = False) -> Settings:
    return Settings(
        mode="demo", allowed_origins={"http://127.0.0.1:4321"}, rate_limit=2, rate_window_seconds=60,
        reticulum_config_dir=None, storage_dir=tmp_path, telegram_bot_token=None, telegram_chat_id=None,
        printer_enabled=enabled, printer_base_url="http://nginx:8082", printer_show_filename=show_filename,
    )


def app_with_printer(tmp_path, fake: FakeMoonraker, clock: FakeClock | None = None, *, show_filename: bool = False):
    app = create_app(settings_for(tmp_path, show_filename=show_filename))
    app.state.printer = make_client(tmp_path / "printer-client", fake, clock, show_filename=show_filename)
    return app


def _prepare_printing(client: PrinterLabClient) -> tuple:
    client.status()
    key = client.take_pending_model()
    assert key is not None
    client.prepare_model(key)
    return key


# Settings

def test_printer_lab_is_disabled_by_default_and_its_settings_are_validated(monkeypatch):
    for name in ("SIGNAL_RELAY_PRINTER_ENABLED", "SIGNAL_RELAY_PRINTER_BASE_URL", "SIGNAL_RELAY_PRINTER_SHOW_FILENAME"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_environment()

    assert settings.printer_enabled is False
    assert settings.printer_show_filename is False
    assert settings.printer_base_url is None


def test_enabling_the_printer_lab_requires_a_base_url(monkeypatch):
    monkeypatch.setenv("SIGNAL_RELAY_PRINTER_ENABLED", "true")
    monkeypatch.delenv("SIGNAL_RELAY_PRINTER_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="SIGNAL_RELAY_PRINTER_BASE_URL"):
        Settings.from_environment()


@pytest.mark.parametrize("bad_url", [
    "https://nginx:8082",
    "http://operator:secret-pass@nginx:8082",
    "http://nginx:8082/printer",
    "http://nginx:8082?filename=x",
    "nginx:8082",
    "http://nginx:not-a-port",
])
def test_printer_base_url_must_be_a_plain_http_origin_and_is_never_echoed(monkeypatch, bad_url):
    monkeypatch.setenv("SIGNAL_RELAY_PRINTER_BASE_URL", bad_url)

    with pytest.raises(ValueError) as error:
        Settings.from_environment()

    assert "SIGNAL_RELAY_PRINTER_BASE_URL" in str(error.value)
    assert "secret-pass" not in str(error.value)


def test_a_valid_printer_base_url_and_switches_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("SIGNAL_RELAY_PRINTER_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_RELAY_PRINTER_BASE_URL", "http://nginx:8082/")
    monkeypatch.setenv("SIGNAL_RELAY_PRINTER_SHOW_FILENAME", "true")

    settings = Settings.from_environment()

    assert settings.printer_enabled is True
    assert settings.printer_show_filename is True
    assert settings.printer_base_url == "http://nginx:8082"


# Routes: disabled and invalid

def test_printer_routes_are_not_served_when_the_lab_is_disabled(tmp_path):
    app = create_app(settings_for(tmp_path, enabled=False))

    assert app.state.printer is None
    with TestClient(app) as client:
        assert client.get("/v1/lab/printer").status_code == 404
        assert client.get("/v1/lab/printer/thumbnail").status_code == 404
        assert client.get(f"/v1/lab/printer/model/{'a' * 32}").status_code == 404


@pytest.mark.parametrize("model_id", ["A" * 32, "a" * 31, "a" * 33, "g" * 32, "0" * 31 + "Z", "%2e%2e" + "a" * 29])
def test_model_route_rejects_anything_but_thirty_two_lowercase_hex_digits(tmp_path, model_id):
    fake = printing_fake()
    with TestClient(app_with_printer(tmp_path, fake)) as client:
        assert client.get(f"/v1/lab/printer/model/{model_id}").status_code == 404


def test_model_route_does_not_serve_an_unknown_but_well_formed_id(tmp_path):
    fake = printing_fake()
    with TestClient(app_with_printer(tmp_path, fake)) as client:
        assert client.get(f"/v1/lab/printer/model/{'0' * 32}").status_code == 404


# Status projection

def test_idle_printer_reports_no_model_and_fetches_only_the_status_query(tmp_path):
    fake = printing_fake(state="standby")
    client = make_client(tmp_path, fake)

    status = client.status()

    assert status["state"] == "idle"
    assert status["progress"] is None
    assert status["layer"] == {"current": None, "total": None}
    assert status["modelId"] is None
    assert status["thumbnail"] is False
    assert fake.targets == [STATUS_TARGET]


def test_printing_reports_progress_layer_height_and_an_opaque_model_id_once_the_model_is_parsed(tmp_path):
    clock = FakeClock()
    fake = printing_fake(position=SECOND_LAYER_OFFSET + 5)
    client = make_client(tmp_path, fake, clock)

    first = client.status()
    assert first["state"] == "printing"
    assert first["progress"] == 0.5
    assert first["modelId"] is None
    assert first["layer"] == {"current": None, "total": None}

    key = client.take_pending_model()
    assert key is not None
    client.prepare_model(key)
    clock.advance(6)
    status = client.status()

    assert MODEL_ID.fullmatch(status["modelId"])
    assert status["layer"] == {"current": 2, "total": 2}
    assert status["heightMm"] == 0.4
    assert status["objectHeightMm"] == 1.0
    assert status["thumbnail"] is True
    assert status["updatedAt"].endswith("Z")


def test_layer_is_null_before_the_first_layer_change_is_passed(tmp_path):
    clock = FakeClock()
    # The header line keeps position 0 in front of the first ;LAYER_CHANGE, which starts at byte 4.
    fake = printing_fake(position=0, gcode="G28\n" + PRINT_GCODE)
    client = make_client(tmp_path, fake, clock)
    _prepare_printing(client)
    clock.advance(6)

    status = client.status()

    assert status["modelId"] is not None
    assert status["layer"]["current"] is None
    assert status["heightMm"] is None


def test_layer_comes_from_moonraker_layer_info_when_no_model_is_cached(tmp_path):
    fake = FakeMoonraker()
    fake.status = status_payload(
        "printing", None, None, 0.2, {"current_layer": 3, "total_layer": 40},
    )
    status = make_client(tmp_path, fake).status()

    assert status["layer"] == {"current": 3, "total": 40}
    assert status["heightMm"] is None
    assert status["modelId"] is None


def test_progress_outside_the_unit_interval_is_not_published(tmp_path):
    fake = printing_fake()
    fake.status = status_payload("printing", None, None, 1.7)

    assert make_client(tmp_path, fake).status()["progress"] is None


@pytest.mark.parametrize("state, expected", [
    ("paused", "paused"),
    ("complete", "complete"),
    ("cancelled", "cancelled"),
    ("error", "error"),
])
def test_print_states_map_to_the_public_vocabulary(tmp_path, state, expected):
    fake = printing_fake(state=state)

    assert make_client(tmp_path, fake).status()["state"] == expected


@pytest.mark.parametrize("failure", ["unreachable", "http_500", "malformed", "unknown_state", "missing_status"])
def test_klipper_and_transport_failures_are_reported_as_unavailable_with_no_model(tmp_path, failure):
    fake = printing_fake()
    if failure == "unreachable":
        fake.unreachable = True
    elif failure == "http_500":
        fake.status = None
    elif failure == "malformed":
        fake.raw_status = b"<html>bad gateway</html>"
    elif failure == "unknown_state":
        fake.status = status_payload("homing", "benchy.gcode", 0)
    else:
        fake.status = {"result": {}}

    status = make_client(tmp_path, fake).status()

    assert status["state"] == "unavailable"
    assert status["progress"] is None
    assert status["modelId"] is None
    assert status["thumbnail"] is False


def test_filename_is_never_published_unless_the_operator_opts_in(tmp_path):
    fake = printing_fake()
    client = make_client(tmp_path, fake)

    status = client.status()

    assert "filename" not in status
    assert "benchy" not in json.dumps(status)


def test_filename_is_published_only_when_the_operator_opts_in(tmp_path):
    fake = printing_fake()

    status = make_client(tmp_path, fake, show_filename=True).status()

    assert status["filename"] == "benchy.gcode"


def test_model_id_is_opaque_stable_across_restarts_and_depends_on_the_relay_salt(tmp_path):
    fake = printing_fake()
    clock = FakeClock()
    first = make_client(tmp_path / "relay", fake, clock)
    _prepare_printing(first)
    clock.advance(6)
    model_id = first.status()["modelId"]

    assert MODEL_ID.fullmatch(model_id)
    assert "benchy" not in model_id
    assert model_id != hashlib.sha256(b"benchy.gcode").hexdigest()[:32]

    restarted = make_client(tmp_path / "relay", fake, FakeClock())
    assert restarted.status()["modelId"] == model_id

    other_clock = FakeClock()
    other_relay = make_client(tmp_path / "other-relay", printing_fake(), other_clock)
    _prepare_printing(other_relay)
    other_clock.advance(6)
    other_id = other_relay.status()["modelId"]
    assert MODEL_ID.fullmatch(other_id)
    assert other_id != model_id


def test_a_truncated_salt_file_is_replaced_with_a_full_random_key(tmp_path):
    salt_path = tmp_path / "relay" / "printer-lab" / "salt"
    make_client(tmp_path / "relay", printing_fake())._load_salt()
    salt_path.write_bytes(b"")

    client = make_client(tmp_path / "relay", printing_fake())
    client._load_salt()

    assert len(salt_path.read_bytes()) == 32
    assert MODEL_ID.fullmatch(client._model_id(("benchy.gcode", 1, 1.0)))


def test_status_query_string_is_exactly_print_stats_and_virtual_sdcard(tmp_path):
    fake = printing_fake()
    make_client(tmp_path, fake).status()

    assert fake.targets[0] == "/printer/objects/query?print_stats&virtual_sdcard"


def test_only_allowlisted_nginx_targets_are_ever_requested(tmp_path):
    fake = printing_fake(position=SECOND_LAYER_OFFSET + 5)
    client = make_client(tmp_path, fake)
    _prepare_printing(client)
    client.thumbnail()
    client.model("0" * 32)

    assert fake.targets
    for target in fake.targets:
        path, _, query = target.partition("?")
        if target == STATUS_TARGET:
            continue
        if path == "/server/files/metadata":
            assert EDGE_METADATA_ARGUMENT.fullmatch(query), "the edge would refuse this metadata query"
        elif path.startswith("/server/files/gcodes/.thumbs/"):
            assert query == ""
            assert THUMBNAIL_NAME.fullmatch(path[len("/server/files/gcodes/"):])
        elif path.startswith("/server/files/gcodes/"):
            assert query == ""
            assert GCODE_NAME.fullmatch(unquote(path[len("/server/files/gcodes/"):]))
        else:
            pytest.fail(f"unexpected target {target}")


@pytest.mark.parametrize("filename", [
    "../secret.gcode",
    "sub/benchy.gcode",
    "a..b.gcode",
    "benchy;rm.gcode",
    "benchy.bgcode",
    "benchy?.gcode",
    "benchy%2e.gcode",
])
def test_filenames_outside_the_allowlist_are_never_requested(tmp_path, filename):
    fake = printing_fake(filename=filename, position=5)
    client = make_client(tmp_path, fake)

    status = client.status()

    assert status["state"] == "printing"
    assert status["progress"] == 0.5
    assert status["modelId"] is None
    assert client.take_pending_model() is None
    assert [target for target in fake.targets if target != STATUS_TARGET] == []


def test_concurrent_polls_within_the_cache_window_cause_one_upstream_call(tmp_path):
    fake = printing_fake()
    gate = threading.Event()
    fake.status_gate = gate
    client = make_client(tmp_path, fake, FakeClock())
    results: list[dict] = []
    threads = [threading.Thread(target=lambda: results.append(client.status())) for _ in range(5)]

    for thread in threads:
        thread.start()
    assert fake.entered.wait(5)
    gate.set()
    for thread in threads:
        thread.join(5)

    assert len(results) == 5
    assert fake.targets.count(STATUS_TARGET) == 1


def test_status_is_reused_for_five_seconds_and_then_refreshed(tmp_path):
    fake = printing_fake()
    clock = FakeClock()
    client = make_client(tmp_path, fake, clock)

    client.status()
    clock.advance(4.9)
    client.status()
    assert fake.targets.count(STATUS_TARGET) == 1

    clock.advance(0.2)
    client.status()
    assert fake.targets.count(STATUS_TARGET) == 2


def test_each_request_uses_the_documented_read_timeouts(tmp_path):
    fake = printing_fake()
    client = make_client(tmp_path, fake)
    _prepare_printing(client)

    timeouts = dict(fake.timeouts)
    assert timeouts[STATUS_TARGET] == 10
    assert timeouts["/server/files/gcodes/benchy.gcode"] == 30


# Model download, cache, and caps

def test_a_model_is_parsed_once_and_survives_a_restart_without_another_download(tmp_path):
    fake = printing_fake()
    client = make_client(tmp_path / "relay", fake)
    key = _prepare_printing(client)

    client.prepare_model(key)
    assert fake.count("/server/files/gcodes/") == 1

    restarted = make_client(tmp_path / "relay", fake, FakeClock())
    restarted.status()
    assert restarted.take_pending_model() is None
    restarted.prepare_model(key)
    assert fake.count("/server/files/gcodes/") == 1


def test_a_corrupt_cached_model_is_removed_and_parsed_again_once(tmp_path):
    fake = printing_fake()
    client = make_client(tmp_path / "relay", fake)
    key = _prepare_printing(client)
    model_id = client._model_id(key)
    (tmp_path / "relay" / "printer-lab" / "models" / f"{model_id}.json").write_text("{not json", encoding="utf-8")

    clock = FakeClock()
    restarted = make_client(tmp_path / "relay", fake, clock)
    assert restarted.status()["modelId"] is None
    assert restarted.take_pending_model() == key
    restarted.prepare_model(key)

    assert fake.count("/server/files/gcodes/") == 2
    clock.advance(6)
    assert restarted.status()["modelId"] == model_id


def test_a_failed_download_backs_off_for_five_minutes_and_is_not_retried_in_a_loop(tmp_path):
    fake = printing_fake()
    fake.gcode_status = 429
    clock = FakeClock()
    client = make_client(tmp_path, fake, clock)
    key = _prepare_printing(client)
    assert fake.count("/server/files/gcodes/") == 1

    clock.advance(299)
    client.prepare_model(key)
    assert fake.count("/server/files/gcodes/") == 1

    clock.advance(2)
    fake.gcode_status = 200
    client.prepare_model(key)
    assert fake.count("/server/files/gcodes/") == 2


def test_only_one_download_runs_at_a_time(tmp_path):
    fake = printing_fake()
    gate = threading.Event()
    fake.gcode_gate = gate
    client = make_client(tmp_path, fake)
    client.status()
    key = client.take_pending_model()
    assert key is not None
    worker = threading.Thread(target=client.prepare_model, args=(key,))

    worker.start()
    assert fake.gcode_entered.wait(5)
    client.prepare_model(key)
    assert fake.count("/server/files/gcodes/") == 1

    gate.set()
    worker.join(5)
    assert not worker.is_alive()
    assert fake.count("/server/files/gcodes/") == 1


def test_a_declared_length_above_the_cap_is_refused_without_reading_the_body(tmp_path):
    fake = printing_fake()
    fake.gcode_content_length = 10**9
    client = make_client(tmp_path, fake, max_gcode_bytes=4096)
    key = _prepare_printing(client)

    assert fake.gcode_responses[0].bytes_read == 0
    assert fake.gcode_responses[0].closed is True
    client.prepare_model(key)
    assert fake.count("/server/files/gcodes/") == 1


def test_a_stream_above_the_cap_is_cut_off_without_a_record(tmp_path):
    big_gcode = "G1 X1 Y1 E1\n" * 20_000
    fake = printing_fake(gcode=big_gcode)
    fake.gcode_content_length = None
    client = make_client(tmp_path, fake, max_gcode_bytes=4096)
    key = _prepare_printing(client)

    assert fake.gcode_responses[0].bytes_read < len(big_gcode.encode())
    assert client.status()["modelId"] is None
    client.prepare_model(key)
    assert fake.count("/server/files/gcodes/") == 1


def test_model_files_on_disk_are_pruned_to_the_newest_eight(tmp_path):
    fake = FakeMoonraker()
    client = make_client(tmp_path, fake)
    for index in range(10):
        name = f"part-{index}.gcode"
        fake.gcode[name] = PRINT_GCODE.encode()
        client.prepare_model((name, len(PRINT_GCODE.encode()), 1_700_000_000.25))

    model_files = list((tmp_path / "printer-lab" / "models").glob("*.json"))
    assert len(model_files) == 8


def test_the_background_worker_parses_only_while_printing(tmp_path):
    fake = printing_fake()
    clock = FakeClock()
    client = make_client(tmp_path, fake, clock)

    async def run() -> None:
        worker = PrinterModelWorker()
        fake.status = status_payload("standby", None)
        client.status()
        assert worker.start(client) is None
        assert fake.count("/server/files/gcodes/") == 0

        fake.status = status_payload("printing", "benchy.gcode", 0)
        clock.advance(6)
        client.status()
        task = worker.start(client)
        assert task is not None
        await task
        assert worker.start(client) is None
        worker.stop()

    asyncio.run(run())
    assert fake.count("/server/files/gcodes/") == 1


# Thumbnail

def test_thumbnail_is_the_largest_png_of_the_current_job_and_is_cached(tmp_path):
    fake = printing_fake()
    client = make_client(tmp_path, fake)

    assert client.thumbnail() == PNG
    assert client.thumbnail() == PNG
    assert fake.count("/server/files/gcodes/.thumbs/benchy-400x300.png") == 1
    assert fake.count("/server/files/gcodes/.thumbs/benchy-32x32.png") == 0


def test_concurrent_thumbnail_requests_for_one_job_share_a_single_read(tmp_path):
    fake = printing_fake()
    gate = threading.Event()
    fake.thumbnail_gate = gate
    client = make_client(tmp_path, fake)
    results: list[bytes | None] = []
    threads = [threading.Thread(target=lambda: results.append(client.thumbnail())) for _ in range(3)]

    for thread in threads:
        thread.start()
    assert fake.thumbnail_entered.wait(5)
    gate.set()
    for thread in threads:
        thread.join(5)

    assert results == [PNG, PNG, PNG]
    assert fake.count("/server/files/gcodes/.thumbs/") == 1


def test_thumbnail_must_be_a_png_under_the_size_cap(tmp_path):
    fake = printing_fake()
    fake.thumbnails[".thumbs/benchy-400x300.png"] = b"GIF89a" + b"0" * 32
    assert make_client(tmp_path / "gif", fake).thumbnail() is None

    fake = printing_fake()
    fake.thumbnails[".thumbs/benchy-400x300.png"] = PNG + b"0" * (512 * 1024)
    assert make_client(tmp_path / "big", fake).thumbnail() is None


def test_thumbnail_paths_outside_the_allowlist_are_never_requested(tmp_path):
    fake = printing_fake()
    metadata = metadata_payload(len(PRINT_GCODE.encode()))
    metadata["thumbnails"] = [{"width": 400, "height": 300, "relative_path": "../../secret.png"}]
    fake.metadata["benchy.gcode"] = metadata

    assert make_client(tmp_path, fake).thumbnail() is None
    assert fake.count("/server/files/gcodes/") == 0


def test_a_failed_thumbnail_is_not_fetched_again_in_the_backoff_window(tmp_path):
    fake = printing_fake()
    fake.thumbnail_error = True
    clock = FakeClock()
    client = make_client(tmp_path, fake, clock)

    assert client.thumbnail() is None
    assert client.thumbnail() is None
    assert fake.count("/server/files/gcodes/.thumbs/") == 1


def test_thumbnail_route_serves_png_only_and_404s_when_there_is_none(tmp_path):
    fake = printing_fake()
    with TestClient(app_with_printer(tmp_path, fake)) as client:
        response = client.get("/v1/lab/printer/thumbnail")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content == PNG
        assert response.headers["cache-control"] == "no-store"

    empty = printing_fake(state="standby")
    with TestClient(app_with_printer(tmp_path / "idle", empty)) as client:
        assert client.get("/v1/lab/printer/thumbnail").status_code == 404


# Routes

def test_status_route_is_served_without_store_and_never_leaks_the_filename(tmp_path):
    fake = printing_fake(position=SECOND_LAYER_OFFSET + 5)
    app = app_with_printer(tmp_path, fake)
    with TestClient(app) as client:
        response = client.get("/v1/lab/printer")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "benchy" not in response.text
    assert response.json()["state"] == "printing"


def test_model_route_serves_the_current_model_without_the_filename(tmp_path):
    fake = printing_fake(position=SECOND_LAYER_OFFSET + 5)
    clock = FakeClock()
    app = app_with_printer(tmp_path, fake, clock)
    client_printer = app.state.printer
    client_printer.status()
    key = client_printer.take_pending_model()
    assert key is not None
    client_printer.prepare_model(key)
    clock.advance(6)
    with TestClient(app) as client:
        model_id = client.get("/v1/lab/printer").json()["modelId"]

        response = client.get(f"/v1/lab/printer/model/{model_id}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, max-age=3600"
    body = response.json()
    assert body["layerCount"] == 2
    assert len(body["layers"]) == 2
    assert set(body) == {"layerHeight", "layerCount", "bbox", "layers"}
    assert "benchy" not in response.text


def test_nginx_transport_sends_only_the_fixed_target_to_the_configured_origin():
    """A loopback stand-in for the edge: the real http.client path, with no printer and no LAN address involved."""
    body = b'{"result": {"status": {}}}'
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *arguments) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        transport = NginxTransport(f"http://127.0.0.1:{server.server_port}")
        response = transport.get(STATUS_TARGET, read_timeout=5)
        try:
            assert response.status == 200
            assert response.content_length == len(body)
            assert response.read(1024) == body
        finally:
            response.close()
    finally:
        server.shutdown()
        server.server_close()

    assert seen == [STATUS_TARGET]


def test_klipper_outage_still_answers_200_unavailable_through_the_route(tmp_path):
    fake = printing_fake()
    fake.unreachable = True
    with TestClient(app_with_printer(tmp_path, fake)) as client:
        response = client.get("/v1/lab/printer")

    assert response.status_code == 200
    assert response.json()["state"] == "unavailable"


def test_a_gcode_file_that_cannot_be_parsed_is_downloaded_once_and_never_retried(tmp_path):
    hostile = ";LAYER_CHANGE\n;Z:0.2\n;HEIGHT:0.2\n;TYPE:Outer wall\nG1 X300000000 Y0 E1\nG1 X0 Y0 E2\n;TYPE:Inner wall\n"
    fake = printing_fake(gcode=hostile)
    clock = FakeClock()
    client = make_client(tmp_path / "relay", fake, clock)

    client.status()
    key = client.take_pending_model()
    assert key is not None
    client.prepare_model(key)

    for _ in range(3):
        clock.advance(10)
        client.status()
        assert client.take_pending_model() is None
    assert fake.count("/server/files/gcodes/") == 1


def test_an_unexpected_parser_error_is_contained_and_not_retried(tmp_path, monkeypatch):
    fake = printing_fake()
    clock = FakeClock()
    client = make_client(tmp_path / "relay", fake, clock)
    monkeypatch.setattr("signal_relay.printer.parse_gcode", lambda chunks: (_ for _ in ()).throw(RuntimeError("boom")))

    client.status()
    key = client.take_pending_model()
    client.prepare_model(key)

    clock.advance(10)
    client.status()
    assert client.take_pending_model() is None
    assert fake.count("/server/files/gcodes/") == 1


def _poll_three_times_and_count_downloads(client, clock, fake, key):
    client.prepare_model(key)
    for _ in range(3):
        clock.advance(10)
        client.status()
        pending = client.take_pending_model()
        if pending is not None:
            client.prepare_model(pending)
    return fake.count("/server/files/gcodes/")


def test_an_unexpected_transport_error_backs_off_instead_of_downloading_again_on_every_poll(tmp_path):
    fake = printing_fake()
    fake.gcode_get_error = ValueError("boom")
    clock = FakeClock()
    client = make_client(tmp_path / "relay", fake, clock)
    client.status()
    key = client.take_pending_model()

    assert _poll_three_times_and_count_downloads(client, clock, fake, key) == 1

    clock.advance(301)
    client.status()
    assert client.take_pending_model() is not None, "the download is attempted again once the backoff has passed"


def test_an_unexpected_storage_error_backs_off_instead_of_downloading_again_on_every_poll(tmp_path, monkeypatch):
    fake = printing_fake()
    clock = FakeClock()
    client = make_client(tmp_path / "relay", fake, clock)

    def broken_write(model_id, parsed):
        raise TypeError("boom")

    monkeypatch.setattr(client, "_write_model", broken_write)
    client.status()
    key = client.take_pending_model()

    assert _poll_three_times_and_count_downloads(client, clock, fake, key) == 1


def test_a_corrupt_stream_backs_off_but_does_not_condemn_a_valid_file(tmp_path):
    fake = printing_fake()
    fake.gcode_read_error = ValueError("invalid chunk size")
    clock = FakeClock()
    client = make_client(tmp_path / "relay", fake, clock)
    client.status()
    key = client.take_pending_model()

    assert _poll_three_times_and_count_downloads(client, clock, fake, key) == 1

    fake.gcode_read_error = None
    clock.advance(301)
    client.status()
    retry = client.take_pending_model()
    assert retry == key, "a network fault must not reject the file for the life of the process"
    client.prepare_model(retry)
    assert fake.count("/server/files/gcodes/") == 2
    clock.advance(10)
    assert client.model(client.status()["modelId"]) is not None


@pytest.mark.parametrize("filename", ["part+2.gcode", "a+b c.gcode"])
def test_filenames_with_a_plus_sign_are_not_requested_because_the_edge_cannot_pass_them(tmp_path, filename):
    fake = printing_fake(filename=filename, position=5)
    client = make_client(tmp_path / "relay", fake)

    status = client.status()

    assert status["state"] == "printing" and status["progress"] is not None
    assert status["modelId"] is None
    assert not any(target.startswith("/server/files/") for target in fake.targets)


@pytest.mark.parametrize("path", [".thumbs/benchy-5x5.png", ".thumbs/benchy-40000x30000.png", ".thumbs/benchy-٤٠٠x٣٠٠.png"])
def test_thumbnail_paths_the_edge_would_refuse_are_not_requested(tmp_path, path):
    fake = printing_fake()
    fake.metadata["benchy.gcode"]["thumbnails"] = [{"width": 400, "height": 300, "size": 900, "relative_path": path}]
    fake.thumbnails[path] = PNG
    client = make_client(tmp_path / "relay", fake)
    client.status()

    assert client.thumbnail() is None
    assert fake.count("/server/files/gcodes/.thumbs/") == 0


def test_a_failure_while_closing_the_download_still_backs_off(tmp_path):
    fake = printing_fake()
    fake.gcode_close_error = OSError("close failed")
    clock = FakeClock()
    client = make_client(tmp_path / "relay", fake, clock)
    client.status()
    key = client.take_pending_model()

    client.prepare_model(key)  # a failing close must be contained like any other download failure

    for _ in range(3):
        clock.advance(10)
        client.status()
        assert client.take_pending_model() is None
    assert fake.count("/server/files/gcodes/") == 1


def test_the_backoff_is_cleared_once_a_model_is_stored_so_the_next_job_is_not_delayed(tmp_path):
    fake = printing_fake()
    clock = FakeClock()
    client = make_client(tmp_path / "relay", fake, clock)
    key = _prepare_printing(client)
    assert key is not None

    fake.status = status_payload("printing", "next.gcode", 0)
    fake.metadata["next.gcode"] = metadata_payload(len(PRINT_GCODE.encode()))
    fake.gcode["next.gcode"] = PRINT_GCODE.encode()
    clock.advance(10)
    client.status()

    assert client.take_pending_model() is not None


def test_a_body_shorter_than_its_content_length_is_never_published_as_a_model(tmp_path):
    fake = printing_fake()
    fake.gcode_content_length = len(PRINT_GCODE.encode()) + 500
    clock = FakeClock()
    client = make_client(tmp_path / "relay", fake, clock)
    client.status()
    key = client.take_pending_model()
    client.prepare_model(key)

    clock.advance(10)
    status = client.status()
    assert status["modelId"] is None
    assert not list((tmp_path / "relay").rglob("*.json")), "nothing may be cached from a truncated download"

    fake.gcode_content_length = "body"
    clock.advance(301)
    client.status()
    client.prepare_model(client.take_pending_model())
    clock.advance(10)
    assert client.status()["modelId"] is not None


def test_a_truncated_thumbnail_is_not_cached(tmp_path):
    fake = printing_fake()
    client = make_client(tmp_path / "relay", fake)
    client.status()
    original = fake.thumbnails[".thumbs/benchy-400x300.png"]
    fake.thumbnails[".thumbs/benchy-400x300.png"] = original

    real_get = fake.get

    def truncated(target, read_timeout):
        response = real_get(target, read_timeout)
        if ".thumbs/" in target and response.status == 200:
            response.content_length = len(original) + 100
        return response

    fake.get = truncated

    assert client.thumbnail() is None


def test_an_unexpected_thumbnail_transport_error_is_not_retried_on_every_request(tmp_path):
    fake = printing_fake()
    fake.thumbnail_get_error = ValueError("boom")
    client = make_client(tmp_path / "relay", fake)
    client.status()

    for _ in range(4):
        assert client.thumbnail() is None
    assert fake.count("/server/files/gcodes/.thumbs/") == 1


def test_a_deeply_nested_status_response_is_contained_and_shares_the_single_flight_cache(tmp_path):
    fake = printing_fake()
    fake.raw_status = b"[" * 120_000 + b"]" * 120_000
    client = make_client(tmp_path / "relay", fake)

    for _ in range(3):
        assert client.status()["state"] == "unavailable"
    assert fake.targets.count(STATUS_TARGET) == 1


# A Moonraker that accepts the connection but never answers must not tie up the shared worker pool: followers wait
# briefly for the in-flight call and then answer from what they already know.

def _in_background(function):
    thread = threading.Thread(target=function, daemon=True)
    thread.start()
    return thread


def test_a_hung_status_poll_does_not_hold_other_requests_and_they_get_the_last_known_state(tmp_path, monkeypatch):
    monkeypatch.setattr(printer_module, "_FOLLOWER_WAIT_SECONDS", 0.05)
    fake = printing_fake()
    clock = FakeClock()
    client = make_client(tmp_path, fake, clock)
    assert client.status()["state"] == "printing"

    clock.advance(10)
    gate = threading.Event()
    fake.status_gate = gate
    fake.entered.clear()
    leader = _in_background(client.status)
    assert fake.entered.wait(5)

    started = time.monotonic()
    follower = client.status()
    elapsed = time.monotonic() - started
    gate.set()
    leader.join(5)

    assert elapsed < 1.0, "a follower must not wait for the whole upstream timeout"
    assert follower["state"] == "printing", "a follower answers from the last known snapshot"
    assert fake.targets.count(STATUS_TARGET) == 2, "followers never start a second upstream call"


def test_a_hung_first_poll_answers_unavailable_to_followers_instead_of_blocking_them(tmp_path, monkeypatch):
    monkeypatch.setattr(printer_module, "_FOLLOWER_WAIT_SECONDS", 0.05)
    fake = printing_fake()
    gate = threading.Event()
    fake.status_gate = gate
    client = make_client(tmp_path, fake)
    leader = _in_background(client.status)
    assert fake.entered.wait(5)

    started = time.monotonic()
    follower = client.status()
    elapsed = time.monotonic() - started
    gate.set()
    leader.join(5)

    assert elapsed < 1.0
    assert follower["state"] == "unavailable"
    assert fake.targets.count(STATUS_TARGET) == 1


def test_a_hung_thumbnail_download_does_not_hold_other_thumbnail_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(printer_module, "_FOLLOWER_WAIT_SECONDS", 0.05)
    fake = printing_fake()
    gate = threading.Event()
    fake.thumbnail_gate = gate
    client = make_client(tmp_path, fake)
    client.status()
    leader = _in_background(client.thumbnail)
    assert fake.thumbnail_entered.wait(5)

    started = time.monotonic()
    follower = client.thumbnail()
    elapsed = time.monotonic() - started
    gate.set()
    leader.join(5)

    assert elapsed < 1.0
    assert follower is None
    assert fake.count("/server/files/gcodes/.thumbs/") == 1
    assert client.thumbnail() == PNG, "the next request is served from the finished download"


def test_a_snapshot_never_advertises_a_thumbnail_the_thumbnail_route_cannot_serve(tmp_path):
    fake = printing_fake()
    del fake.metadata["benchy.gcode"]["modified"]
    client = make_client(tmp_path, fake)

    status = client.status()

    assert status["thumbnail"] is False
    assert client.thumbnail() is None


def test_a_cached_thumbnail_is_served_even_while_another_thumbnail_download_is_in_flight(tmp_path, monkeypatch):
    monkeypatch.setattr(printer_module, "_FOLLOWER_WAIT_SECONDS", 0.05)
    fake = printing_fake()
    client = make_client(tmp_path, fake)
    client.status()
    assert client.thumbnail() == PNG

    assert client._thumbnail_lock.acquire(timeout=1)  # another request is downloading a thumbnail right now
    try:
        assert client.thumbnail() == PNG
    finally:
        client._thumbnail_lock.release()
