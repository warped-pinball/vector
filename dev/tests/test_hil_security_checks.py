"""Tests for the parts of the HIL security checks that do not need a board.

The made up update packages are the subtle part: each one has to get past the
board's own hash check, or be meant to fail it, so that a refusal comes from
the gate under test. So they are checked with the board's own parser.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# bench.py imports pyserial (which ships with mpremote) and dev/usb_coms_demo.
# Neither is needed here, so stand them in before the import.
_serial_stub = sys.modules.setdefault("serial", types.ModuleType("serial"))
if not hasattr(_serial_stub, "SerialTimeoutException"):
    _serial_stub.SerialTimeoutException = type("SerialTimeoutException", (Exception,), {})
if "usb_coms_demo" not in sys.modules:
    stub = types.ModuleType("usb_coms_demo")
    stub.UsbApiClient = object
    sys.modules["usb_coms_demo"] = stub

sys.path.insert(0, str(REPO_ROOT / "dev" / "hil"))

import security_checks as sc  # noqa: E402


def board_update_module():
    """src/common/update.py, the board's own update code, loaded under CPython."""
    spec = importlib.util.spec_from_file_location("board_update", REPO_ROOT / "src" / "common" / "update.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_passes_the_boards_hash_check(tmp_path, monkeypatch):
    package, digest = sc.update_package()
    path = tmp_path / "update.json"
    path.write_bytes(package)
    monkeypatch.chdir(tmp_path)

    hash_bytes, expected_hash, signature = board_update_module().get_check_data(str(path))

    assert hash_bytes == expected_hash
    assert hash_bytes.hex() == digest
    assert signature


def test_corrupt_package_fails_the_boards_hash_check(tmp_path):
    package, digest = sc.update_package(corrupt=True)
    path = tmp_path / "update.json"
    path.write_bytes(package)

    hash_bytes, expected_hash, _signature = board_update_module().get_check_data(str(path))

    assert hash_bytes != expected_hash
    assert expected_hash.hex() == digest


def test_package_last_line_is_the_signature_record():
    package, digest = sc.update_package()
    last = json.loads(package.rstrip(b"\n").rsplit(b"\n", 1)[1])
    assert last["sha256"] == digest
    assert set(last) == {"sha256", "signature"}


def test_sign_matches_the_web_ui_message_layout():
    # challenge + path + body, as utils.js smartFetch builds it
    expected = hmac.new(b"pw", b"abc/api/update/apply" + b'{"url":"x"}', hashlib.sha256).hexdigest()
    assert sc.sign("pw", "abc", "/api/update/apply", sc.compact({"url": "x"})) == expected


def test_compact_matches_json_stringify_spacing():
    assert sc.compact({"url": "x", "skip_signature_check": True}) == '{"url":"x","skip_signature_check":true}'
