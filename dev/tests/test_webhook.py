import sys
import types
from pathlib import Path

import pytest

COMMON_SRC = str(Path(__file__).resolve().parents[2] / "src" / "common")


@pytest.fixture
def webhook(monkeypatch, tmp_path):
    """Import src/common/webhook.py under CPython with the MicroPython bits stubbed."""
    micropython = types.ModuleType("micropython")
    micropython.const = lambda value: value
    monkeypatch.setitem(sys.modules, "micropython", micropython)

    origin = types.ModuleType("origin")
    origin.get_machine_id = lambda: "deadbeef"
    monkeypatch.setitem(sys.modules, "origin", origin)

    monkeypatch.setitem(sys.modules, "ujson", __import__("json"))
    monkeypatch.syspath_prepend(COMMON_SRC)
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("webhook", None)
    import webhook as module

    yield module
    sys.modules.pop("webhook", None)


def test_parse_url_defaults_port_and_path(webhook):
    assert webhook.parse_url("https://example.com") == ("example.com", 443, "/")
    assert webhook.parse_url("https://example.com:8443/hooks/vector?x=1") == ("example.com", 8443, "/hooks/vector?x=1")


@pytest.mark.parametrize("url", ["http://example.com/hook", "https:///hook", "example.com"])
def test_parse_url_rejects_non_https(webhook, url):
    with pytest.raises(ValueError):
        webhook.parse_url(url)


def test_send_does_nothing_without_a_target(webhook):
    webhook.send("reset")
    assert webhook.get_status()["queued"] == 0


def test_target_survives_a_fresh_import_and_clear_forgets_it(webhook):
    webhook.set_target("https://example.com/hook", "s3cret")

    webhook._loaded = False
    webhook._url = None
    assert webhook.get_status()["url"] == "https://example.com/hook"
    assert "s3cret" not in str(webhook.get_status())

    webhook.clear_target()
    webhook._loaded = False
    assert webhook.get_status()["url"] is None


def test_send_numbers_messages_and_drops_the_oldest_when_full(webhook):
    import json

    webhook.set_target("https://example.com/hook", "s3cret")
    for i in range(webhook._MAX_QUEUE + 2):
        webhook.send("end_of_game", {"game_num": i})

    bodies = [json.loads(entry[0]) for entry in webhook._queue]
    assert len(bodies) == webhook._MAX_QUEUE
    assert bodies[0]["n"] == 3
    assert bodies[-1] == {"machine_id": "deadbeef", "type": "end_of_game", "n": webhook._MAX_QUEUE + 2, "data": {"game_num": webhook._MAX_QUEUE + 1}}
