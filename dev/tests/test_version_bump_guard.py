from dev.ci import version_bump_guard as vbg


def test_touches_scope_detects_prefix() -> None:
    changed = ["src/em/GameStatus.py", "docs/README.md"]

    assert vbg.touches_scope(changed, ("src/em/",)) is True
    assert vbg.touches_scope(changed, ("src/wpc/",)) is False


def test_evaluate_rules_passes_when_required_versions_changed() -> None:
    changed = ["src/common/backend.py", "src/em/sensorRead.py"]
    results = {
        "common shared-state version (all src changes)": True,
        "EM system config version": True,
    }

    failures = vbg.evaluate_rules(changed, results)

    assert failures == []


def test_evaluate_rules_fails_for_missing_required_bumps() -> None:
    changed = ["src/common/backend.py", "src/data_east/DataMapper.py", "src/wpc/ScoreTrack.py"]
    results = {
        "common shared-state version (all src changes)": False,
        "Data East system config version": False,
        "WPC system config version": True,
    }

    failures = vbg.evaluate_rules(changed, results)

    assert len(failures) == 2
    assert "src/common/" in failures[0]
    assert "src/common/SharedState.py" in failures[0]
    assert "src/data_east/" in failures[1]
    assert "src/data_east/systemConfig.py" in failures[1]


def test_evaluate_rules_reports_all_missing_bumps() -> None:
    changed = [
        "src/common/backend.py",
        "src/em/DiagDisplay.py",
        "src/sys11/DataMapper.py",
    ]
    results = {
        "common shared-state version (all src changes)": False,
        "EM system config version": False,
        "System11 system config version": False,
    }

    failures = vbg.evaluate_rules(changed, results)

    assert len(failures) == 3
    assert any("src/common/SharedState.py" in failure for failure in failures)
    assert any("src/em/systemConfig.py" in failure for failure in failures)
    assert any("src/sys11/systemConfig.py" in failure for failure in failures)


def test_em_change_also_requires_common_bump() -> None:
    changed = ["src/em/sensorRead.py"]
    results = {
        "common shared-state version (all src changes)": False,
        "EM system config version": True,
    }

    failures = vbg.evaluate_rules(changed, results)

    assert len(failures) == 1
    assert "src/common/SharedState.py" in failures[0]


def test_semver_patch_bump() -> None:
    semver = vbg.SemVer.parse("1.6.9", "test.py")

    assert str(semver.bump_patch()) == "1.6.10"


def test_analyze_rule_requires_patch_when_pr_not_higher(monkeypatch) -> None:
    rule = vbg.RULES[1]
    changed = ["src/em/GameStatus.py"]

    monkeypatch.setattr(
        vbg,
        "version_at_ref",
        lambda ref, file_path, pattern: "1.5.2" if ref == "base" else "1.5.2",
    )

    outcome = vbg.analyze_rule(rule, changed, "base", "head")

    assert outcome.requires_bump is True
    assert outcome.target_version == "1.5.3"


def test_analyze_rule_passes_when_pr_is_higher(monkeypatch) -> None:
    rule = vbg.RULES[1]
    changed = ["src/em/GameStatus.py"]

    monkeypatch.setattr(
        vbg,
        "version_at_ref",
        lambda ref, file_path, pattern: "1.5.2" if ref == "base" else "1.6.0",
    )

    outcome = vbg.analyze_rule(rule, changed, "base", "head")

    assert outcome.requires_bump is False
    assert outcome.target_version is None
