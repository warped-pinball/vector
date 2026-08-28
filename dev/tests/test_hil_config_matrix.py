"""Tests for the parts of the HIL config matrix that do not need a board.

Everything that touches serial, mpremote or a real board is out of reach here;
what is testable is the expectation side - how the harness reads the repo's
config JSON, which configs it decides to run, and in what order - plus the
filename-length rule that decides whether a config can be reached at all.
"""

from __future__ import annotations

import json
import sys
import time
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


def responder(responses):
    """A stand-in for bench.get over a fake board."""

    def fake_get(_client, route, expect=200):
        body = responses[route]
        if isinstance(body, Exception):
            raise body
        return body

    return fake_get


def healthy(config="AttackMars_11", name="Attack from Mars"):
    return {
        # HDWR02 is expected on a bare bench board with nothing driving the bus.
        "/api/fault": ["HDWR02: No Bus Activity"],
        "/api/game/active_config": {"active_config": config},
        "/api/game/name": name,
        "/api/leaders": [],
        "/api/adjustments/status": {"profiles": [], "adjustments_support": True},
    }


def test_check_booted_config_passes_when_the_board_reports_the_configured_game(monkeypatch):
    monkeypatch.setattr(cm, "get", responder(healthy()))

    name = cm.check_booted_config(FakeClient(), "wpc", "AttackMars_11", {"name": "Attack from Mars", "adjustments": True})

    assert name == "Attack from Mars"


def test_check_booted_config_catches_a_silent_fallback_to_the_generic_config(monkeypatch):
    """The failure this harness exists for.

    A config that fails to apply raises nothing an outside observer can see:
    GameDefsLoad drops to safe_defaults and the board serves a generic
    definition, healthy in every other respect. Only the game name gives it
    away.
    """
    monkeypatch.setattr(cm, "get", responder(healthy(name="Generic System")))

    with pytest.raises(bench.CheckFailure, match="fell back to a generic definition"):
        cm.check_booted_config(FakeClient(), "wpc", "AttackMars_11", {"name": "Attack from Mars", "adjustments": True})


def test_check_booted_config_catches_a_board_running_a_different_config(monkeypatch):
    monkeypatch.setattr(cm, "get", responder(healthy(config="Taxi_L4")))

    with pytest.raises(bench.CheckFailure, match="active config is 'Taxi_L4'"):
        cm.check_booted_config(FakeClient(), "wpc", "AttackMars_11", {"name": "Attack from Mars", "adjustments": True})


def test_check_booted_config_accepts_the_game_name_as_the_active_config_on_em(monkeypatch):
    # EM answers /api/game/active_config with the game name (backend.py:481).
    monkeypatch.setattr(cm, "get", responder(healthy(config="EM Machine", name="EM Machine")))

    name = cm.check_booted_config(FakeClient(), "em", "EM_machine_", {"name": "EM Machine", "adjustments": False})

    assert name == "EM Machine"


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
    monkeypatch.setattr(cm, "get", responder({"/api/fault": faults}))

    with pytest.raises(bench.CheckFailure, match=expected):
        cm.check_faults(FakeClient(), "AttackMars_11")


def test_check_faults_allows_the_bare_bench_fault(monkeypatch):
    monkeypatch.setattr(cm, "get", responder({"/api/fault": ["HDWR02: No Bus Activity"]}))

    cm.check_faults(FakeClient(), "AttackMars_11")


def test_check_adjustments_fails_when_the_config_declares_the_section(monkeypatch):
    monkeypatch.setattr(cm, "get", responder({"/api/adjustments/status": bench.CheckFailure("returned 500")}))

    with pytest.raises(bench.CheckFailure, match="500"):
        cm.check_adjustments(FakeClient(), "AttackMars_11", declares_adjustments=True)


def test_check_adjustments_only_warns_for_a_config_with_no_adjustments(monkeypatch, capsys):
    # A known firmware gap rather than a config problem - see check_adjustments().
    monkeypatch.setattr(cm, "get", responder({"/api/adjustments/status": bench.CheckFailure("returned 500")}))

    cm.check_adjustments(FakeClient(), "Taxi_L4", declares_adjustments=False)

    assert "::warning::Taxi_L4" in capsys.readouterr().out


def test_check_bundle_reports_a_config_missing_from_the_build(monkeypatch):
    monkeypatch.setattr(cm, "get", responder({"/api/game/configs_list": {"Taxi_L4": {"name": "Taxi"}}}))

    with pytest.raises(bench.CheckFailure, match="AttackMars_11"):
        cm.check_bundle(FakeClient(), "wpc", {"Taxi_L4": {"name": "Taxi"}, "AttackMars_11": {"name": "Attack from Mars"}})


def test_check_bundle_reports_a_game_name_that_drifted_from_the_source(monkeypatch):
    monkeypatch.setattr(cm, "get", responder({"/api/game/configs_list": {"Taxi_L4": {"name": "Taksi"}}}))

    with pytest.raises(bench.CheckFailure, match="bundle says 'Taksi'"):
        cm.check_bundle(FakeClient(), "wpc", {"Taxi_L4": {"name": "Taxi"}})


# --------------------------------------------------------------------------
# the matrix loop, and what it does when a board stops answering
# --------------------------------------------------------------------------


class FakeSession:
    """Stands in for a board. `dies_after` makes it stop answering mid-run."""

    def __init__(self, port, boot_timeout=None, dies_after=None):
        self.port = port
        self.boot_timeout = boot_timeout
        self.dies_after = dies_after
        self.connection = object()
        self.client = FakeClient()
        self.boot_log = []
        self.configs_set = []
        self.boots = 0
        self.starts = 0
        self.nudges = 0
        self.restored = False

    def start(self):
        self.starts += 1
        return self.wait_for_boot()

    def wait_for_boot(self):
        self.boots += 1
        if self.dies_after is not None and self.boots > self.dies_after:
            self.client = None
            self.connection = None
            raise bench.CheckFailure(f"{self.port} never reported its web server within 90s")
        self.client = FakeClient()
        self.connection = object()
        return self.client

    def set_config(self, gamename):
        if self.client is None:
            raise bench.CheckFailure(f"could not reach the REPL on {self.port}")
        self.configs_set.append(gamename)

    def reboot(self):
        self.connection = None

    def nudge(self):
        self.nudges += 1
        self.close()

    def close(self):
        self.connection = None
        self.client = None


def run_board(monkeypatch, fake_repo, session, check=None, **arg_overrides):
    """Drive run_matrix against a fake board. `check` replaces the assertions."""
    if check is None:

        def check(_client, _target, _config, expected):
            return expected["name"]

    monkeypatch.setattr(cm, "Session", lambda port, boot_timeout=None: session)
    monkeypatch.setattr(cm, "check_bundle", lambda *a, **k: None)
    monkeypatch.setattr(cm, "check_booted_config", check)
    monkeypatch.setattr(cm, "restore_default", lambda s, _target: setattr(s, "restored", True))

    defaults = {"configs": None, "limit": None, "changed_since": None, "keep_going": True, "boot_timeout": 90, "config_timeout": 60}
    defaults.update(arg_overrides)
    return cm.run_matrix({"port": session.port, "target": "wpc"}, Namespace(**defaults))


def test_run_matrix_walks_every_config_on_a_healthy_board(monkeypatch, fake_repo):
    session = FakeSession("/dev/ttyFAKE")

    passed, failures = run_board(monkeypatch, fake_repo, session)

    assert failures == []
    assert passed == ["AttackMars_11", "Generic_WPC", "Taxi_L4"]
    assert session.configs_set == passed
    assert session.restored is True


def test_run_matrix_abandons_a_board_that_stops_answering(monkeypatch, fake_repo):
    """The 63-minute failure, in one test.

    The first bench run wrote the same timeout 63 times against a WPC board
    that had wedged one config in. Two consecutive setup failures is enough to
    know the board is gone.
    """
    # Enough configs that abandoning the board leaves some unrun - the point
    # being that we stop rather than time out against every one of them.
    config_dir = fake_repo / "src" / "wpc" / "config"
    for index in range(6):
        write_config(config_dir, f"Filler_L{index}", f"Filler {index}", Adjustments={"Type": 0})

    # Boot 1 is the bundle check and boot 2 is the first config, so the board
    # survives exactly one config before going quiet.
    session = FakeSession("/dev/ttyFAKE", dies_after=2)

    passed, failures = run_board(monkeypatch, fake_repo, session)

    assert len(passed) == 1
    assert session.boots <= 1 + cm.MAX_CONSECUTIVE_SETUP_FAILURES
    assert any("skipped after" in reason for _config, reason in failures)
    # Every setup failure gets one cheap recovery attempt before we give up.
    assert session.nudges == cm.MAX_CONSECUTIVE_SETUP_FAILURES
    # Teardown still runs, so the next job does not inherit a stranded board.
    assert session.restored is True


def test_run_matrix_keeps_going_after_a_failing_config(monkeypatch, fake_repo):
    """An assertion failure is a result about the config, not about the board."""

    def one_bad_config(_client, _target, config, expected):
        if config == "Generic_WPC":
            raise bench.CheckFailure("board reports game name 'Generic System' - fell back to a generic definition")
        return expected["name"]

    session = FakeSession("/dev/ttyFAKE")
    passed, failures = run_board(monkeypatch, fake_repo, session, check=one_bad_config)

    assert passed == ["AttackMars_11", "Taxi_L4"]
    assert [config for config, _reason in failures] == ["Generic_WPC"]


def test_run_matrix_stops_at_the_first_failure_when_asked(monkeypatch, fake_repo):
    def always_fails(*_args, **_kwargs):
        raise bench.CheckFailure("board reports game name 'Generic System'")

    session = FakeSession("/dev/ttyFAKE")
    passed, failures = run_board(monkeypatch, fake_repo, session, check=always_fails, keep_going=False)

    assert passed == []
    assert len(failures) == 1


def test_restore_default_never_raises_when_the_board_is_gone(capsys):
    """Teardown must not throw away results the matrix already produced.

    The first bench run died exactly here: a TimeoutExpired escaped teardown,
    took out the run summary, and skipped the board that had not been touched
    yet.
    """

    class DeadSession:
        port = "/dev/ttyFAKE"
        connection = None

        def wait_for_boot(self):
            raise TimeoutError("board is not coming back")

        def close(self):
            pass

    cm.restore_default(DeadSession(), "wpc")

    assert "::warning::could not restore Generic_WPC" in capsys.readouterr().out


# --------------------------------------------------------------------------
# raw REPL framing
# --------------------------------------------------------------------------


class FakeSerial:
    """Replays a scripted board response and records what was written."""

    def __init__(self, script=b""):
        self.script = bytearray(script)
        self.written = bytearray()

    def read(self, size=1):
        chunk = bytes(self.script[:size])
        del self.script[: len(chunk)]
        return chunk

    @property
    def in_waiting(self):
        return len(self.script)

    def write(self, data):
        self.written.extend(data)
        return len(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass

    def close(self):
        pass


def test_repl_enter_syncs_past_application_output():
    # The board is mid-sentence when we interrupt it, so the banner arrives
    # after whatever it was printing.
    serial = FakeSerial(b"RESOURCE: RAM=69%\r\nTraceback\r\nraw REPL; CTRL-B to exit\r\n>")

    bench.Repl(serial).enter(timeout=1)

    assert bench.CTRL_C in serial.written
    assert bench.CTRL_A in serial.written


def test_repl_enter_reports_the_console_when_the_board_does_not_answer():
    serial = FakeSerial(b"RESOURCE: RAM=69%\r\n")

    with pytest.raises(bench.CheckFailure, match="raw REPL prompt"):
        bench.Repl(serial).enter(timeout=0.2)


def test_repl_keeps_bytes_that_arrive_past_a_marker():
    """The bug that made the first version of this desynchronise.

    A read that syncs on `OK` almost always pulls in the output that follows
    it; discarding that made every later marker arrive at an empty stream.
    """
    repl = bench.Repl(FakeSerial(b"OKGAMENAME=Taxi_L4\x04\x04>"))

    assert repl.read_until(b"OK", 1, "ok") == b""
    assert repl.read_until(bench.CTRL_D, 1, "output") == b"GAMENAME=Taxi_L4"


def test_repl_exec_returns_what_the_snippet_printed():
    serial = FakeSerial(b"OKGAMENAME=Taxi_L4\r\n\x04\x04>")

    output = bench.Repl(serial).exec("print('x')", timeout=1)

    assert "GAMENAME=Taxi_L4" in output
    assert serial.written.endswith(bench.CTRL_D)


def test_repl_exec_surfaces_a_traceback_from_the_board():
    serial = FakeSerial(b"OK\x04Traceback (most recent call last):\r\n  KeyError: nope\x04>")

    with pytest.raises(bench.CheckFailure, match="KeyError: nope"):
        bench.Repl(serial).exec("boom", timeout=1)


def fake_repl(monkeypatch, output):
    class StubRepl:
        def __init__(self, _connection):
            pass

        def enter(self, timeout=None):
            return self

        def exec(self, _code, timeout=None):
            return output

    monkeypatch.setattr(bench, "Repl", StubRepl)


def test_set_game_config_rejects_a_name_the_board_truncated(monkeypatch):
    fake_repl(monkeypatch, "GAMENAME=HarleyDavidson_L\r\n")

    with pytest.raises(bench.CheckFailure, match="16 bytes and this filename is 17"):
        bench.set_game_config(FakeSerial(), "HarleyDavidson_L3")


def test_set_game_config_accepts_a_clean_round_trip(monkeypatch):
    fake_repl(monkeypatch, "GAMENAME=Taxi_L4\r\n")

    bench.set_game_config(FakeSerial(), "Taxi_L4")


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


# --------------------------------------------------------------------------
# not hanging on a board that has stopped listening
# --------------------------------------------------------------------------


def test_open_serial_always_sets_a_write_timeout(monkeypatch):
    """The bug that hung a bench job for 30 minutes.

    `serial.Serial(timeout=...)` sets the READ timeout only. Without a
    write_timeout, writing to a board that has stopped draining its USB
    endpoint blocks forever - which is precisely the board the recovery tool
    exists to write to.
    """
    opened = {}

    def fake_serial(**kwargs):
        opened.update(kwargs)
        return FakeSerial()

    monkeypatch.setattr(bench.serial, "Serial", fake_serial, raising=False)
    bench.open_serial("/dev/ttyFAKE")

    assert opened["timeout"] == bench.SERIAL_READ_TIMEOUT
    assert opened["write_timeout"] == bench.SERIAL_WRITE_TIMEOUT


def test_serial_write_turns_a_stuck_board_into_an_error(monkeypatch):
    monkeypatch.setattr(bench.serial, "SerialTimeoutException", RuntimeError, raising=False)

    class Deaf:
        def write(self, _data):
            raise RuntimeError("write timed out")

    with pytest.raises(bench.CheckFailure, match="stopped draining its USB endpoint"):
        bench.serial_write(Deaf(), b"\x03", "the board")


def test_repl_never_calls_flush():
    """flush() is tcdrain, which takes no timeout and hangs on the same board.

    Handing the bytes to the kernel is enough; every exchange here is
    synchronised by a read with a deadline instead.
    """
    source = (REPO_ROOT / "dev" / "hil" / "bench.py").read_text()

    assert ".flush()" not in source


def test_time_limit_interrupts_work_that_overruns():
    with pytest.raises(bench.CheckFailure, match="did not finish within"):
        with bench.time_limit(1, "a step that hangs"):
            time.sleep(5)


def test_time_limit_is_invisible_when_work_finishes_in_time():
    with bench.time_limit(5, "quick work"):
        result = 1 + 1

    assert result == 2


def test_time_limit_restores_the_previous_handler():
    import signal

    before = signal.getsignal(signal.SIGALRM)
    with bench.time_limit(5, "quick work"):
        pass

    assert signal.getsignal(signal.SIGALRM) is before


def test_run_matrix_resets_the_board_before_watching_its_first_boot(monkeypatch, fake_repo):
    """The regression that failed all three boards without checking one config.

    The ready marker is printed once per boot. dev/flash.py resets at the end
    of flashing and flashing runs over every board first, so by the time the
    matrix opens a console the board booted minutes ago and the marker is gone.
    Every later boot is triggered by reboot(); the first one has to be
    triggered by start().
    """
    session = FakeSession("/dev/ttyFAKE")

    run_board(monkeypatch, fake_repo, session)

    assert session.starts == 1, "the first boot must be preceded by a reset"


def test_session_start_resets_then_waits(monkeypatch):
    """start() is a reset plus a wait, in that order."""
    order = []
    monkeypatch.setattr(cm, "reset_board", lambda port: order.append(f"reset {port}"))
    monkeypatch.setattr(cm, "wait_for_server", lambda port, timeout=None: (order.append("wait"), (types.SimpleNamespace(close=lambda: None), []))[1])
    monkeypatch.setattr(cm, "prime_usb", lambda _connection: None)
    monkeypatch.setattr(cm, "UsbApiClient", lambda _connection: FakeClient())

    cm.Session("/dev/ttyFAKE").start()

    assert order == ["reset /dev/ttyFAKE", "wait"]
