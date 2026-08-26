"""Tests for the parts of the HIL config matrix that do not need a board.

Everything that touches serial, mpremote or a real board is out of reach here;
what is testable is the expectation side - how the harness reads the repo's
config JSON, which configs it decides to run, and in what order - plus the
filename-length rule that decides whether a config can be reached at all.
"""

from __future__ import annotations

import json
import sys
import types
from argparse import Namespace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# bench.py imports pyserial (which ships with mpremote) and dev/usb_coms_demo.
# Neither is needed for the pure helpers under test and neither is guaranteed to
# be installed wherever these tests run, so stand them in before the import.
sys.modules.setdefault("serial", types.ModuleType("serial"))
if "usb_coms_demo" not in sys.modules:
    stub = types.ModuleType("usb_coms_demo")
    stub.UsbApiClient = object
    sys.modules["usb_coms_demo"] = stub

sys.path.insert(0, str(REPO_ROOT / "dev" / "hil"))

import bench  # noqa: E402
import config_matrix as cm  # noqa: E402


def write_config(directory: Path, name: str, game_name: str, **sections) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"GameInfo": {"GameName": game_name, "System": "WPC"}}
    payload.update(sections)
    (directory / f"{name}.json").write_text(json.dumps(payload))


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    """A repo-shaped tree with one target and three configs."""
    config_dir = tmp_path / "src" / "wpc" / "config"
    write_config(config_dir, "AttackMars_11", "Attack from Mars", Adjustments={"Type": 0})
    write_config(config_dir, "Generic_WPC", "Generic System WPC", Adjustments={"Type": 0})
    write_config(config_dir, "Taxi_L4", "Taxi")
    monkeypatch.setattr(cm, "REPO_ROOT", tmp_path)
    return tmp_path


def args(**overrides) -> Namespace:
    defaults = {"configs": None, "limit": None, "changed_since": None}
    defaults.update(overrides)
    return Namespace(**defaults)


def test_source_configs_reads_names_and_adjustments(fake_repo):
    configs = cm.source_configs("wpc")

    assert configs["AttackMars_11"] == {"name": "Attack from Mars", "adjustments": True}
    # Taxi_L4 declares no Adjustments section, which is what decides whether
    # /api/adjustments/status is held to 200 on the bench.
    assert configs["Taxi_L4"] == {"name": "Taxi", "adjustments": False}


def test_source_configs_rejects_a_config_with_no_game_name(fake_repo):
    (fake_repo / "src" / "wpc" / "config" / "Broken_L1.json").write_text(json.dumps({"GameInfo": {}}))

    with pytest.raises(bench.CheckFailure, match="GameInfo.GameName"):
        cm.source_configs("wpc")


def test_source_configs_rejects_unparseable_json(fake_repo):
    (fake_repo / "src" / "wpc" / "config" / "Broken_L1.json").write_text("{nope")

    with pytest.raises(bench.CheckFailure, match="not valid JSON"):
        cm.source_configs("wpc")


def test_source_configs_rejects_an_unknown_target(fake_repo):
    with pytest.raises(bench.CheckFailure, match="no config directory"):
        cm.source_configs("nosuchtarget")


def test_select_configs_defaults_to_every_config(fake_repo):
    names, configs = cm.select_configs("wpc", args())

    assert names == sorted(configs) == ["AttackMars_11", "Generic_WPC", "Taxi_L4"]


def test_select_configs_honours_an_explicit_list(fake_repo):
    names, _ = cm.select_configs("wpc", args(configs="Taxi_L4, AttackMars_11"))

    assert names == ["Taxi_L4", "AttackMars_11"]


def test_select_configs_rejects_an_unknown_name(fake_repo):
    with pytest.raises(bench.CheckFailure, match="Nonexistent_L1"):
        cm.select_configs("wpc", args(configs="Nonexistent_L1"))


def test_select_configs_applies_the_limit(fake_repo):
    names, _ = cm.select_configs("wpc", args(limit=2))

    assert names == ["AttackMars_11", "Generic_WPC"]


def test_select_configs_runs_changed_configs_first(fake_repo, monkeypatch):
    monkeypatch.setattr(cm, "changed_configs", lambda target, ref: ["Taxi_L4"])

    names, _ = cm.select_configs("wpc", args(changed_since="origin/main"))

    assert names[0] == "Taxi_L4"
    assert sorted(names) == ["AttackMars_11", "Generic_WPC", "Taxi_L4"]


def test_order_configs_ignores_names_that_are_not_under_test():
    ordered = cm.order_configs(["a", "b", "c"], ["c", "deleted"])

    assert ordered == ["c", "a", "b"]


def test_order_configs_is_a_no_op_without_changes():
    assert cm.order_configs(["a", "b"], []) == ["a", "b"]


def test_gamename_field_width_comes_from_the_firmware_source():
    # Not hard-coded in the harness: widening the FRAM field in SPI_DataStore.py
    # must move this number, or the harness would keep enforcing a stale limit.
    assert bench.gamename_field_bytes() == 16


# Two shipped WPC configs are longer than the FRAM `gamename` field and so can
# never be selected on a real board: the web UI offers them, the write is
# accepted, the name is truncated on the way into FRAM, and the next boot
# matches nothing and comes up on safe defaults with CONF01 raised. That is a
# pre-existing firmware/config defect, not something this harness introduced -
# it is what the bench found first - so it is recorded here rather than fixed
# here. Shortening either filename (or widening the field) should shorten this
# list; nothing should ever lengthen it.
KNOWN_UNREACHABLE_CONFIGS = {"GilliganIsland_L9", "HarleyDavidson_L3"}


def test_no_new_config_name_exceeds_the_gamename_field():
    """A config whose filename is longer than the field can never be selected.

    write_record packs `gamename` into a fixed-width field and struct.pack
    truncates silently, so the truncated name matches nothing at boot and the
    board comes up on safe defaults with CONF01. The bench catches this per
    board, but it is cheaper to catch here, and this way a new offender fails
    an ordinary PR rather than 20 minutes of bench time.
    """
    limit = bench.gamename_field_bytes()
    too_long = {path.stem for path in (REPO_ROOT / "src").glob("*/config/*.json") if len(path.stem.encode()) > limit}

    new_offenders = sorted(too_long - KNOWN_UNREACHABLE_CONFIGS)
    assert new_offenders == [], f"config filenames longer than the {limit}-byte FRAM gamename field: {', '.join(new_offenders)}"

    fixed = sorted(KNOWN_UNREACHABLE_CONFIGS - too_long)
    assert fixed == [], f"{', '.join(fixed)} now fits - drop it from KNOWN_UNREACHABLE_CONFIGS"


# --------------------------------------------------------------------------
# the assertions themselves, with the board faked out
# --------------------------------------------------------------------------


class FakeClient:
    def __init__(self, *_args):
        pass

    def close(self):
        pass


def fake_board(monkeypatch, responses, stored=None):
    """Patch out everything that needs hardware; return the recorded writes.

    `responses` maps a route to the body the fake board answers with, or to an
    exception to raise.
    """
    written = []

    def fake_get(_client, route, expect=200):
        body = responses[route]
        if isinstance(body, Exception):
            raise body
        return body

    def fake_set_game_config(_port, gamename):
        if stored is not None and gamename != stored:
            raise bench.CheckFailure(f"wrote gamename={gamename!r} but the board stored {stored!r}")
        written.append(gamename)

    monkeypatch.setattr(cm, "get", fake_get)
    monkeypatch.setattr(cm, "set_game_config", fake_set_game_config)
    monkeypatch.setattr(cm, "reset_board", lambda _port: None)
    monkeypatch.setattr(cm, "prime_usb", lambda _connection: None)
    monkeypatch.setattr(cm, "UsbApiClient", FakeClient)
    monkeypatch.setattr(cm, "wait_for_server", lambda _port, timeout=None: (types.SimpleNamespace(close=lambda: None), ["boot"]))
    return written


def healthy(config="AttackMars_11", name="Attack from Mars"):
    return {
        # HDWR02 is expected on a bare bench board with nothing driving the bus.
        "/api/fault": ["HDWR02: No Bus Activity"],
        "/api/game/active_config": {"active_config": config},
        "/api/game/name": name,
        "/api/leaders": [],
        "/api/adjustments/status": {"profiles": [], "adjustments_support": True},
    }


def test_check_config_passes_when_the_board_reports_the_configured_game(monkeypatch):
    written = fake_board(monkeypatch, healthy())

    name, _boot_log = cm.check_config("/dev/ttyFAKE", "wpc", "AttackMars_11", {"name": "Attack from Mars", "adjustments": True})

    assert name == "Attack from Mars"
    assert written == ["AttackMars_11"]


def test_check_config_catches_a_silent_fallback_to_the_generic_config(monkeypatch):
    """The failure this harness exists for.

    A config that fails to apply raises nothing an outside observer can see:
    GameDefsLoad drops to safe_defaults and the board serves a generic
    definition, healthy in every other respect. Only the game name gives it
    away.
    """
    fake_board(monkeypatch, healthy(name="Generic System"))

    with pytest.raises(bench.CheckFailure, match="fell back to a generic definition"):
        cm.check_config("/dev/ttyFAKE", "wpc", "AttackMars_11", {"name": "Attack from Mars", "adjustments": True})


def test_check_config_catches_a_board_running_a_different_config(monkeypatch):
    fake_board(monkeypatch, healthy(config="Taxi_L4"))

    with pytest.raises(bench.CheckFailure, match="active config is 'Taxi_L4'"):
        cm.check_config("/dev/ttyFAKE", "wpc", "AttackMars_11", {"name": "Attack from Mars", "adjustments": True})


def test_check_config_accepts_the_game_name_as_the_active_config_on_em(monkeypatch):
    # EM answers /api/game/active_config with the game name (backend.py:481).
    fake_board(monkeypatch, healthy(config="EM Machine", name="EM Machine"))

    name, _ = cm.check_config("/dev/ttyFAKE", "em", "EM_machine_", {"name": "EM Machine", "adjustments": False})

    assert name == "EM Machine"


def test_check_config_reports_a_name_that_cannot_be_stored(monkeypatch):
    fake_board(monkeypatch, healthy(), stored="HarleyDavidson_L")

    with pytest.raises(bench.CheckFailure, match="but the board stored"):
        cm.check_config("/dev/ttyFAKE", "wpc", "HarleyDavidson_L3", {"name": "Harley Davidson", "adjustments": True})


@pytest.mark.parametrize(
    "faults, expected",
    [
        (["CONF01: Invalid Configuration"], "safe defaults"),
        (["CONF00: Unknown Configuration Error"], "safe defaults"),
        (["HDWR01: Early Bus Activity"], "safe mode"),
        (["HDWR00: Unknown Hardware Error"], "unexpected fault"),
    ],
)
def test_check_faults_rejects_anything_that_invalidates_the_result(monkeypatch, faults, expected):
    fake_board(monkeypatch, {"/api/fault": faults})

    with pytest.raises(bench.CheckFailure, match=expected):
        cm.check_faults(FakeClient(), "AttackMars_11")


def test_check_faults_allows_the_bare_bench_fault(monkeypatch):
    fake_board(monkeypatch, {"/api/fault": ["HDWR02: No Bus Activity"]})

    cm.check_faults(FakeClient(), "AttackMars_11")


def test_check_adjustments_fails_when_the_config_declares_the_section(monkeypatch):
    fake_board(monkeypatch, {"/api/adjustments/status": bench.CheckFailure("returned 500")})

    with pytest.raises(bench.CheckFailure, match="500"):
        cm.check_adjustments(FakeClient(), "AttackMars_11", declares_adjustments=True)


def test_check_adjustments_only_warns_for_a_config_with_no_adjustments(monkeypatch, capsys):
    # A known firmware gap rather than a config problem - see check_adjustments().
    fake_board(monkeypatch, {"/api/adjustments/status": bench.CheckFailure("returned 500")})

    cm.check_adjustments(FakeClient(), "Taxi_L4", declares_adjustments=False)

    assert "::warning::Taxi_L4" in capsys.readouterr().out


def test_write_step_summary_renders_a_table_and_the_failures(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    cm.write_step_summary([({"port": "/dev/ttyACM0", "target": "wpc"}, ["Taxi_L4"], [("AttackMars_11", "boom\nsecond line")])])

    rendered = summary.read_text()
    assert "| `/dev/ttyACM0` | wpc | 2 | 1 | 1 |" in rendered
    assert "**wpc `AttackMars_11`** - boom" in rendered
    assert "second line" not in rendered


def test_write_step_summary_is_a_no_op_outside_actions(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    cm.write_step_summary([({"port": "/dev/ttyACM0", "target": "wpc"}, [], [])])
