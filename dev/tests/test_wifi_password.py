"""Long WiFi passwords: the extra FRAM record, and what happens on boards that never had it.

Runs every system's SPI_DataStore and the shared WifiPassword module under
CPython, with the FRAM chip replaced by a bytearray.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SYSTEMS = ["common", "wpc", "data_east", "em"]

# Where every record started before the wifi_password record was added. A board
# upgraded to this firmware must find all of its data exactly where it left it.
EXISTING_STARTS = {
    "common": {"configuration": 0x54FB, "extras": 0x54CB, "switches": 0x5483},
    "wpc": {"configuration": 0x4A97, "extras": 0x4A67, "switches": 0x4A1F},
    "data_east": {"configuration": 0x4A97, "extras": 0x4A67},
    "em": {"configuration": 0x54FB, "extras": 0x54CB, "EMData": 0x5403},
}
# Lowest address anything else in FRAM uses (logger end + 1)
FREE_FLOOR = {"common": 0x4400, "wpc": 0x4600, "data_east": 0x4600, "em": 0x4400}


class _Fram:
    def __init__(self, fill=0):
        self.mem = bytearray([fill]) * 0x8000

    def read(self, address, length):
        return bytes(self.mem[address : address + length])

    def write(self, address, data):
        self.mem[address : address + len(data)] = data


class _Log:
    def log(self, *_):
        pass


@pytest.fixture(params=SYSTEMS)
def board(request, monkeypatch):
    system = request.param
    fram = _Fram()
    stubs = {
        "SPI_Store": types.SimpleNamespace(read=fram.read, write=fram.write),
        "logger": types.SimpleNamespace(logger_instance=_Log()),
        "micropython": types.SimpleNamespace(const=lambda value: value),
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    for name in ("SPI_DataStore", "WifiPassword"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.syspath_prepend(str(REPO_ROOT / "src" / "common"))
    monkeypatch.syspath_prepend(str(REPO_ROOT / "src" / system))
    datastore = importlib.import_module("SPI_DataStore")
    wifi = importlib.import_module("WifiPassword")
    assert Path(datastore.__file__).parent.name == system
    return types.SimpleNamespace(system=system, fram=fram, ds=datastore, wifi=wifi)


def _old_firmware_save(board, ssid, password, gamename="game", admin="admin"):
    """What firmware without the long record writes: just the configuration record"""
    board.ds.write_record("configuration", {"ssid": ssid, "password": password, "gamename": gamename, "Gpassword": admin})


def test_existing_records_did_not_move(board):
    for name, start in EXISTING_STARTS[board.system].items():
        assert board.ds.memory_map[name]["start"] == start, name


def test_new_record_sits_in_free_space(board):
    record = board.ds.memory_map["wifi_password"]
    lowest_existing = min(EXISTING_STARTS[board.system].values())
    assert record["start"] + record["size"] == lowest_existing
    assert record["start"] >= FREE_FLOOR[board.system]
    assert record["size"] == 72


def test_63_character_password_round_trips(board):
    password = "p" * 50 + "-0123456789ab"
    assert len(password) == 63
    board.wifi.save_configuration("Arcade", password, "game", "admin")
    config = board.ds.read_record("configuration", 0)
    assert config["password"] == password[:32]
    assert config["ssid"] == "Arcade"
    assert config["Gpassword"] == "admin"
    assert board.wifi.read_password(config) == password
    assert board.wifi.read_password() == password


def test_64_digit_hex_key_round_trips(board):
    key = "0123456789abcdef" * 4
    board.wifi.save_configuration("Arcade", key, "game", "admin")
    assert board.wifi.read_password() == key


def test_short_password_needs_no_long_record(board):
    board.wifi.save_configuration("Arcade", "x" * 63, "game", "admin")
    board.wifi.save_configuration("Arcade", "short-one", "game", "admin")
    assert board.wifi.read_password() == "short-one"
    assert board.ds.read_record("wifi_password", 0)["marker"] == b"\0\0\0\0"


def test_board_from_before_the_record_keeps_its_password(board):
    # FRAM below the data store was never written, so it can hold anything
    record = board.ds.memory_map["wifi_password"]
    board.fram.mem[record["start"] : record["start"] + record["size"]] = bytes(range(200, 200 + 72))
    _old_firmware_save(board, "Arcade", "old-password")
    assert board.wifi.read_password() == "old-password"


def test_settings_saved_by_older_firmware_win_over_a_stale_long_record(board):
    board.wifi.save_configuration("Arcade", "L" * 60, "game", "admin")
    # downgraded, set up again with a new short password, then upgraded
    _old_firmware_save(board, "Arcade", "brand-new")
    assert board.wifi.read_password() == "brand-new"
    # same password prefix but a different network still does not match
    board.wifi.save_configuration("Arcade", "L" * 60, "game", "admin")
    _old_firmware_save(board, "Other", "L" * 32)
    assert board.wifi.read_password() == "L" * 32


def test_multibyte_password_is_cut_on_a_character_boundary(board):
    password = "a" * 31 + "é" + "b" * 20  # é is 2 bytes and straddles byte 32
    board.wifi.save_configuration("Arcade", password, "game", "admin")
    config = board.ds.read_record("configuration", 0)
    assert config["password"] == "a" * 31
    assert board.wifi.read_password(config) == password


def test_factory_reset_clears_the_long_record(board):
    board.wifi.save_configuration("Arcade", "z" * 63, "game", "admin")
    board.ds.blankAll()
    record = board.ds.memory_map["wifi_password"]
    assert board.fram.read(record["start"], record["size"]) == bytes(record["size"])
    assert board.wifi.read_password() == ""
