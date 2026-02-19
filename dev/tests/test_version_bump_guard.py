from dev.ci import version_bump_guard as vbg


def test_touches_scope_detects_prefix() -> None:
    changed = ["src/em/GameStatus.py", "docs/README.md"]

    assert vbg.touches_scope(changed, ("src/em/",)) is True
    assert vbg.touches_scope(changed, ("src/wpc/",)) is False


def test_evaluate_rules_passes_when_required_versions_changed() -> None:
    changed = ["src/common/backend.py", "src/em/sensorRead.py"]
    results = {
        "common shared-state version": True,
        "EM system config version": True,
    }

    failures = vbg.evaluate_rules(changed, results)

    assert failures == []


def test_evaluate_rules_fails_for_missing_required_bumps() -> None:
    changed = ["src/common/backend.py", "src/data_east/DataMapper.py", "src/wpc/ScoreTrack.py"]
    results = {
        "common shared-state version": False,
        "Data East system config version": False,
        "WPC system config version": True,
    }

    failures = vbg.evaluate_rules(changed, results)

    assert len(failures) == 2
    assert "src/common/" in failures[0]
    assert "src/common/SharedState.py" in failures[0]
    assert "src/data_east/" in failures[1]
    assert "src/data_east/systemConfig.py" in failures[1]
