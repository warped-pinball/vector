from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path


def load_usb_comms(monkeypatch, routes):
    class DummyPoll:
        def register(self, *_args, **_kwargs):
            return None

        def poll(self, *_args, **_kwargs):
            return []

    uselect_mod = types.SimpleNamespace(POLLIN=1, poll=lambda: DummyPoll())
    game_status_mod = types.SimpleNamespace(game_report=lambda: {})

    class FakeRequest:
        def __init__(self, method, uri, protocol):
            self.method = method
            self.protocol = protocol
            self.data = {}
            self.headers = {}
            self.path = uri
            self.raw_data = None

    class FakeResponse:
        def __init__(self, body, status=200, headers=None):
            self.body = body
            self.status = status
            self.headers = headers or {}

        def add_header(self, name, value):
            self.headers[name] = value

    server_mod = types.ModuleType("phew.server")
    server_mod.Request = FakeRequest
    server_mod.Response = FakeResponse
    server_mod._routes = routes
    server_mod.catchall_handler = None

    phew_mod = types.ModuleType("phew")
    phew_mod.server = server_mod

    monkeypatch.setitem(sys.modules, "uselect", uselect_mod)
    monkeypatch.setitem(sys.modules, "GameStatus", game_status_mod)
    monkeypatch.setitem(sys.modules, "phew", phew_mod)
    monkeypatch.setitem(sys.modules, "phew.server", server_mod)
    monkeypatch.syspath_prepend(str(Path("src/common").resolve()))

    sys.modules.pop("USB_Comms", None)
    return importlib.import_module("USB_Comms")


def test_handle_usb_api_request_renders_response(monkeypatch):
    routes = {
        "/hello": lambda request: ("hi", 201, {"Content-Type": "text/plain"}),
    }

    usb = load_usb_comms(monkeypatch, routes)

    response_json = usb.handle_usb_api_request(
        "/hello",
        "Content-Type: text/plain\nX-Test: true",
        "",
    )
    payload = json.loads(response_json)

    assert payload["status"] == 201
    assert payload["headers"]["Content-Type"] == "text/plain"
    assert payload["body"] == "hi"


def test_handle_usb_api_request_handles_missing_route(monkeypatch):
    usb = load_usb_comms(monkeypatch, {})

    response_json = usb.handle_usb_api_request("/missing", "", "")
    payload = json.loads(response_json)

    assert payload["status"] == 404
    assert payload["body"] == "Route not found"
