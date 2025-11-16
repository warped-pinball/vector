"""Tests for the backend auth wrapper using stubbed dependencies."""

from __future__ import annotations

import gc
import importlib
import json
import sys
import types


def _install_stub_modules(monkeypatch):
    """Provide lightweight stubs so ``src.common.backend`` can be imported."""

    # ``gc.threshold`` is available on MicroPython but not CPython. Provide a
    # harmless stand-in so ``from gc import threshold`` works during import.
    gc.threshold = lambda *args, **kwargs: None

    def add_module(name: str, module: types.ModuleType):
        monkeypatch.setitem(sys.modules, name, module)
        return module

    add_module("faults", types.ModuleType("faults"))
    add_module("Pico_Led", types.ModuleType("Pico_Led"))
    shared_state = add_module("SharedState", types.ModuleType("SharedState"))
    shared_state.gameCounter = 0
    add_module("uctypes", types.ModuleType("uctypes"))

    ls_module = types.ModuleType("ls")
    ls_module.ls = lambda *args, **kwargs: []
    add_module("ls", ls_module)

    machine_module = types.ModuleType("machine")
    machine_module.RTC = type("RTC", (), {})
    add_module("machine", machine_module)

    shadow_defs = types.ModuleType("Shadow_Ram_Definitions")
    shadow_defs.SRAM_DATA_BASE = 0
    shadow_defs.SRAM_DATA_LENGTH = 0
    add_module("Shadow_Ram_Definitions", shadow_defs)

    spi_datastore = types.ModuleType("SPI_DataStore")
    spi_datastore.memory_map = {}
    spi_datastore.ds_read_record = spi_datastore.read_record = lambda *_, **__: {
        "Gpassword": "secret-password"
    }
    spi_datastore.write_record = lambda *args, **kwargs: None
    add_module("SPI_DataStore", spi_datastore)

    ujson_module = types.ModuleType("ujson")
    ujson_module.dumps = json.dumps
    add_module("ujson", ujson_module)

    # phew.server stubs for routing/response types
    phew_module = add_module("phew", types.ModuleType("phew"))
    phew_server = types.ModuleType("phew.server")

    class Request:
        def __init__(self, method: str, path: str, protocol: str = "HTTP/1.1"):
            self.method = method
            self.path = path
            self.protocol = protocol
            self.is_usb_transport = False
            self.raw_data = ""
            self.data = {}
            self.headers = {}

    class Response:
        def __init__(self, body, status=200, headers=None):
            self.body = body
            self.status = status
            self.headers = headers or {}

        def add_header(self, name, value):
            self.headers[name] = value

    phew_server.Request = Request
    phew_server.Response = Response
    phew_server._routes = {}
    phew_server.catchall_handler = lambda req: Response("", status=404, headers={})

    def add_route(path, handler):
        phew_server._routes[path] = handler

    phew_server.add_route = add_route
    add_module("phew.server", phew_server)
    phew_module.server = phew_server

    phew_ntp = types.ModuleType("phew.ntp")
    phew_ntp.time_ago = lambda *args, **kwargs: "0s"
    add_module("phew.ntp", phew_ntp)
    phew_module.ntp = phew_ntp

    add_module("GameStatus", types.ModuleType("GameStatus"))
    add_module("GameDefsLoad", types.ModuleType("GameDefsLoad"))


def test_require_auth_bypass_only_from_usb(monkeypatch):
    _install_stub_modules(monkeypatch)

    backend = importlib.import_module("src.common.backend")

    calls = {}

    def protected_handler(request):
        calls["called"] = True
        return "ok"

    wrapped = backend.require_auth(protected_handler)

    usb_request = types.SimpleNamespace(
        headers={},
        path="/api/protected",
        raw_data="",
        data={},
        method="USB",
        protocol="USB/1.0",
        is_usb_transport=True,
    )

    assert wrapped(usb_request) == "ok"
    assert calls["called"] is True

    calls.clear()
    http_request = types.SimpleNamespace(
        headers={},
        path="/api/protected",
        raw_data="",
        data={},
        method="GET",
        protocol="HTTP/1.1",
        is_usb_transport=False,
    )

    denial = wrapped(http_request)
    assert "called" not in calls
    assert isinstance(denial, tuple)
    assert denial[1] == 401


def test_require_auth_rejects_http_with_usb_protocol(monkeypatch):
    _install_stub_modules(monkeypatch)

    backend = importlib.import_module("src.common.backend")

    wrapped = backend.require_auth(lambda req: "ok")

    tampered_http_request = types.SimpleNamespace(
        headers={},
        path="/api/protected",
        raw_data="",
        data={},
        method="GET",
        protocol="USB/1.0",  # Spoofed protocol
    )

    denial = wrapped(tampered_http_request)

    assert isinstance(denial, tuple)
    assert denial[1] == 401
