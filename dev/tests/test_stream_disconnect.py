"""What the web server does when a client vanishes part way through a streamed response.

An update streams its progress to the browser while it writes files. A dropped
connection used to abandon the generator where it stood: the update stopped
half way and the board never left low memory mode. These run the board's own
request handler under CPython with the hardware modules stood in.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


@pytest.fixture()
def server(monkeypatch):
    """phew.server imported fresh, with every board only module replaced."""

    async def wait_for_ms(awaitable, timeout_ms):
        return await asyncio.wait_for(awaitable, timeout_ms / 1000)

    async def sleep_ms(ms):
        await asyncio.sleep(ms / 1000)

    class _RTC:
        def datetime(self):
            return (2026, 1, 1, 0, 0, 0, 0, 0)

    class _Log:
        def log(self, *_):
            pass

    stubs = {
        "machine": _stub("machine", RTC=_RTC),
        "logger": _stub("logger", logger_instance=_Log()),
        "faults": _stub("faults"),
        "ntptime": _stub("ntptime"),
        "uasyncio": _stub("uasyncio", get_event_loop=lambda: None, wait_for_ms=wait_for_ms, sleep_ms=sleep_ms),
        "micropython": _stub("micropython", const=lambda value: value),
        "ScoreTrack": _stub("ScoreTrack", CheckForNewScores=None, check_for_machine_high_scores=None, initialize_leaderboard=None),
        "Shadow_Ram_Definitions": _stub("Shadow_Ram_Definitions", SRAM_DATA_BASE=0, SRAM_DATA_LENGTH=0),
        "SPI_Store": _stub("SPI_Store", write_16_fram=None),
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    for name in [m for m in sys.modules if m == "phew" or m.startswith("phew.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(REPO_ROOT / "src" / "common"))
    monkeypatch.setitem(__builtins__ if isinstance(__builtins__, dict) else vars(__builtins__), "const", lambda value: value)

    import phew.server as phew_server

    yield phew_server

    for name in [m for m in sys.modules if m == "phew" or m.startswith("phew.")]:
        sys.modules.pop(name, None)


class _Reader:
    def __init__(self, path):
        self._lines = [f"GET {path} HTTP/1.1\r\n".encode(), b"\r\n"]

    async def readline(self):
        return self._lines.pop(0) if self._lines else b""


class _Writer:
    """Accepts the headers and `good_chunks` body chunks, then the client is gone."""

    def __init__(self, good_chunks):
        self._good_chunks = good_chunks
        self.body = []
        self.closed = False
        self._headers_done = False

    def write(self, data):
        if not self._headers_done:
            self._headers_done = data == b"\r\n"
            return
        if len(self.body) >= self._good_chunks:
            raise OSError(104, "ECONNRESET")
        self.body.append(data)

    async def drain(self):
        pass

    def get_extra_info(self, _):
        return None

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


def _job(steps, record):
    """A streamed job like apply_update: work between yields, cleanup in a finally."""

    def route(request):
        try:
            for step in range(steps):
                record.append(step)
                yield f"step {step}"
            record.append("done")
        finally:
            record.append("cleanup")

    return route


def test_update_style_route_finishes_after_the_client_leaves(server):
    record = []
    server.add_route("/job", _job(5, record))
    server.finish_on_disconnect("/job")
    writer = _Writer(good_chunks=2)

    asyncio.run(server._handle_request(_Reader("/job"), writer))

    assert writer.body == ["step 0", "step 1"]
    assert record == [0, 1, 2, 3, 4, "done", "cleanup"]
    assert writer.closed


def test_other_streams_stop_but_still_clean_up(server):
    record = []
    server.add_route("/download", _job(5, record))
    writer = _Writer(good_chunks=2)

    asyncio.run(server._handle_request(_Reader("/download"), writer))

    # stopped where the client left, and the finally ran instead of being dropped
    assert record == [0, 1, 2, "cleanup"]
    assert writer.closed


def test_a_failure_after_the_client_left_does_not_escape(server):
    record = []

    def route(request):
        yield "one"
        yield "two"
        record.append("working")
        raise RuntimeError("flash write failed")

    server.add_route("/job", route)
    server.finish_on_disconnect("/job")

    asyncio.run(server._handle_request(_Reader("/job"), _Writer(good_chunks=1)))

    assert record == ["working"]


def test_a_healthy_stream_is_untouched(server):
    record = []
    server.add_route("/job", _job(3, record))
    server.finish_on_disconnect("/job")
    writer = _Writer(good_chunks=99)

    asyncio.run(server._handle_request(_Reader("/job"), writer))

    assert writer.body == ["step 0", "step 1", "step 2"]
    assert record == [0, 1, 2, "done", "cleanup"]
