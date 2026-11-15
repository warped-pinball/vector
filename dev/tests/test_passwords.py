"""Long WiFi and admin passwords: the extra FRAM records, and what happens on boards that never had it.

Runs every system's SPI_DataStore and the shared Passwords module under
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
    for name in ("SPI_DataStore", "Passwords", "systemConfig"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.syspath_prepend(str(REPO_ROOT / "src" / "common"))
    monkeypatch.syspath_prepend(str(REPO_ROOT / "src" / system))
    # the common data store is System 11's; its systemConfig comes from src/sys11
    monkeypatch.syspath_prepend(str(REPO_ROOT / "src" / ("sys11" if system == "common" else system)))
    datastore = importlib.import_module("SPI_DataStore")
    pw = importlib.import_module("Passwords")
    assert Path(datastore.__file__).parent.name == system
    return types.SimpleNamespace(system=system, fram=fram, ds=datastore, pw=pw)


def _old_firmware_save(board, ssid, password, gamename="game", admin="admin"):
    """What firmware without the long record writes: just the configuration record"""
    board.ds.write_record("configuration", {"ssid": ssid, "password": password, "gamename": gamename, "Gpassword": admin})


def test_existing_records_did_not_move(board):
    for name, start in EXISTING_STARTS[board.system].items():
        assert board.ds.memory_map[name]["start"] == start, name


def test_new_records_sit_in_free_space(board):
    wifi = board.ds.memory_map["wifi_password"]
    admin = board.ds.memory_map["admin_password"]
    lowest_existing = min(EXISTING_STARTS[board.system].values())
    assert wifi["start"] + wifi["size"] == lowest_existing
    assert admin["start"] + admin["size"] == wifi["start"]
    assert admin["start"] >= FREE_FLOOR[board.system]
    assert wifi["size"] == admin["size"] == 72


def test_63_character_password_round_trips(board):
    password = "p" * 50 + "-0123456789ab"
    assert len(password) == 63
    board.pw.save_configuration("Arcade", password, "game", "admin")
    config = board.ds.read_record("configuration", 0)
    assert config["password"] == password[:32]
    assert config["ssid"] == "Arcade"
    assert config["Gpassword"] == "admin"
    assert board.pw.read_password("wifi", config) == password
    assert board.pw.read_password("wifi") == password


def test_64_digit_hex_key_round_trips(board):
    key = "0123456789abcdef" * 4
    board.pw.save_configuration("Arcade", key, "game", "admin")
    assert board.pw.read_password("wifi") == key


def test_short_password_needs_no_long_record(board):
    board.pw.save_configuration("Arcade", "x" * 63, "game", "admin")
    board.pw.save_configuration("Arcade", "short-one", "game", "admin")
    assert board.pw.read_password("wifi") == "short-one"
    assert board.ds.read_record("wifi_password", 0)["marker"] == b"\0\0\0\0"


def test_board_from_before_the_record_keeps_its_password(board):
    # FRAM below the data store was never written, so it can hold anything
    record = board.ds.memory_map["wifi_password"]
    board.fram.mem[record["start"] : record["start"] + record["size"]] = bytes((200 + i) % 256 for i in range(72))
    _old_firmware_save(board, "Arcade", "old-password")
    assert board.pw.read_password("wifi") == "old-password"


def test_settings_saved_by_older_firmware_win_over_a_stale_long_record(board):
    board.pw.save_configuration("Arcade", "L" * 60, "game", "admin")
    # downgraded, set up again with a new short password, then upgraded
    _old_firmware_save(board, "Arcade", "brand-new")
    assert board.pw.read_password("wifi") == "brand-new"
    # same password prefix but a different network still does not match
    board.pw.save_configuration("Arcade", "L" * 60, "game", "admin")
    _old_firmware_save(board, "Other", "L" * 32)
    assert board.pw.read_password("wifi") == "L" * 32


def test_multibyte_password_is_cut_on_a_character_boundary(board):
    password = "a" * 31 + "é" + "b" * 20  # é is 2 bytes and straddles byte 32
    board.pw.save_configuration("Arcade", password, "game", "admin")
    config = board.ds.read_record("configuration", 0)
    assert config["password"] == "a" * 31
    assert board.pw.read_password("wifi", config) == password


def test_factory_reset_clears_the_long_record(board):
    board.pw.save_configuration("Arcade", "z" * 63, "game", "admin")
    board.pw.save_configuration("Arcade", "z" * 63, "game", "A" * 40)
    board.ds.blankAll()
    for name in ("wifi_password", "admin_password"):
        record = board.ds.memory_map[name]
        assert board.fram.read(record["start"], record["size"]) == bytes(record["size"])
    assert board.pw.read_password("admin") == ""
    assert board.pw.read_password("wifi") == ""


def test_same_network_saved_by_older_firmware_with_the_long_prefix_still_connects(board):
    # older firmware saves exactly the first 32 bytes of the long password: the
    # long record still matches, so the short password has to be tried too
    long_password = "Q" * 40
    board.pw.save_configuration("Arcade", long_password, "game", "admin")
    _old_firmware_save(board, "Arcade", "Q" * 32)
    assert board.pw.passwords_to_try("wifi") == [long_password, "Q" * 32]


def test_one_password_to_try_when_there_is_no_long_record(board):
    board.pw.save_configuration("Arcade", "short-one", "game", "admin")
    assert board.pw.passwords_to_try("wifi") == ["short-one"]


def test_a_failed_long_record_write_changes_nothing_and_raises(board, monkeypatch):
    board.pw.save_configuration("Arcade", "previous", "game", "admin")
    real_write = board.ds.write_record

    def failing_write(structure_name, record, index=0, set=0):
        if structure_name == "wifi_password":
            return {"status": "error", "message": "FRAM write failed"}
        return real_write(structure_name, record, index, set)

    monkeypatch.setattr(board.ds, "write_record", failing_write)
    with pytest.raises(OSError):
        board.pw.save_configuration("Other", "N" * 50, "game", "admin")
    monkeypatch.setattr(board.ds, "write_record", real_write)
    config = board.ds.read_record("configuration", 0)
    assert (config["ssid"], board.pw.read_password("wifi", config)) == ("Arcade", "previous")


def test_a_failed_configuration_write_raises(board, monkeypatch):
    monkeypatch.setattr(board.ds, "write_record", lambda *a, **k: {"status": "error", "message": "FRAM write failed"})
    with pytest.raises(OSError):
        board.pw.save_configuration("Arcade", "short-one", "game", "admin")


def test_long_admin_password_round_trips(board):
    admin = "correct horse battery staple, 40 chars!"
    board.pw.save_configuration("Arcade", "wifi-password", "game", admin)
    config = board.ds.read_record("configuration", 0)
    assert config["Gpassword"] == admin[:16]
    assert board.pw.read_password("admin", config) == admin
    assert board.pw.passwords_to_try("admin", config) == [admin, admin[:16]]
    # the WiFi password is untouched by it
    assert board.pw.passwords_to_try("wifi", config) == ["wifi-password"]


def test_both_long_passwords_are_independent(board):
    board.pw.save_configuration("Arcade", "W" * 63, "game", "A" * 64)
    assert board.pw.read_password("wifi") == "W" * 63
    assert board.pw.read_password("admin") == "A" * 64
    board.pw.save_configuration("Arcade", "W" * 63, "game", "short-admin")
    assert board.pw.read_password("wifi") == "W" * 63
    assert board.pw.passwords_to_try("admin") == ["short-admin"]


def test_admin_password_set_by_older_firmware_is_used(board):
    board.pw.save_configuration("Arcade", "wifi-password", "game", "A" * 40)
    _old_firmware_save(board, "Arcade", "wifi-password", admin="new-admin")
    assert board.pw.passwords_to_try("admin") == ["new-admin"]
