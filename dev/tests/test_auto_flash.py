import subprocess

from dev.auto_flash import build_and_flash


def test_build_once_and_progress(monkeypatch, capfd):
    mapping = {"sys11": ["p1", "p2"], "wpc": ["p3"]}
    builds = []
    popens = []

    def fake_run(cmd, check, stdout=None, stderr=None):
        builds.append((cmd, stdout, stderr))
        return subprocess.CompletedProcess(cmd, 0)

    class FakeProc:
        def wait(self):
            return 0

    def fake_popen(cmd, stdout=None, stderr=None):
        # ensure all builds finished before flashing starts
        assert len(builds) == len(mapping)
        popens.append((cmd, stdout, stderr))
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    build_and_flash(mapping)

    assert len(builds) == 2
    assert len(popens) == 3
    out = capfd.readouterr().out.strip().splitlines()
    assert out == [
        "1 of 3 boards complete",
        "2 of 3 boards complete",
        "3 of 3 boards complete",
    ]


def test_quiet_and_verbose_modes(monkeypatch):
    captured = {}

    def fake_run(cmd, check, stdout=None, stderr=None):
        captured.setdefault("build", []).append((stdout, stderr))
        return subprocess.CompletedProcess(cmd, 0)

    class FakeProc:
        def wait(self):
            return 0

    def fake_popen(cmd, stdout=None, stderr=None):
        captured.setdefault("flash", []).append((stdout, stderr))
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    build_and_flash({"sys11": ["p1", "p2"]})
    build_and_flash({"sys11": ["p1"]})

    # first call (quiet) uses DEVNULL
    build_stdout, _ = captured["build"][0]
    flash_stdout, _ = captured["flash"][0]
    assert build_stdout is subprocess.DEVNULL
    assert flash_stdout is subprocess.DEVNULL

    # second call (verbose) leaves streams alone
    build_stdout, _ = captured["build"][-1]
    flash_stdout, _ = captured["flash"][-1]
    assert build_stdout is None
    assert flash_stdout is None
