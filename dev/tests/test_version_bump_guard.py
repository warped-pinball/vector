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


def test_apply_bumps_updates_version_file(tmp_path) -> None:
    # Create a temporary version file with a simple semantic version string
    version_file = tmp_path / "version_file.py"
    original_content = '__version__ = "1.2.3"\n'
    version_file.write_text(original_content)

    # Regex with three capture groups: prefix, version, suffix
    pattern = r'(__version__\s*=\s*")(\d+\.\d+\.\d+)(")'

    class DummyRule:
        def __init__(self, description, scope, file_path, pattern):
            self.description = description
            self.scope = scope
            self.file_path = file_path
            self.pattern = pattern

    class DummyOutcome:
        def __init__(self, rule, requires_bump, target_version):
            self.rule = rule
            self.requires_bump = requires_bump
            self.target_version = target_version

    rule = DummyRule("test apply_bumps", (), str(version_file), pattern)
    outcome = DummyOutcome(rule=rule, requires_bump=True, target_version="1.2.4")

    # Call apply_bumps and assert that it reports the updated file
    updated_files = vbg.apply_bumps([outcome], dry_run=False)

    assert updated_files == [str(version_file)]

    # Verify that the file content was updated with the target version
    updated_content = version_file.read_text()
    assert '__version__ = "1.2.4"' in updated_content
    assert "1.2.3" not in updated_content


def test_apply_bumps_raises_when_pattern_does_not_match(tmp_path) -> None:
    # Create a file that does not contain a version string matching the pattern
    version_file = tmp_path / "no_match_version_file.py"
    version_file.write_text("no version here\n")

    pattern = r'(__version__\s*=\s*")(\d+\.\d+\.\d+)(")'

    class DummyRule:
        def __init__(self, description, scope, file_path, pattern):
            self.description = description
            self.scope = scope
            self.file_path = file_path
            self.pattern = pattern

    class DummyOutcome:
        def __init__(self, rule, requires_bump, target_version):
            self.rule = rule
            self.requires_bump = requires_bump
            self.target_version = target_version

    rule = DummyRule("test apply_bumps no match", (), str(version_file), pattern)
    outcome = DummyOutcome(rule=rule, requires_bump=True, target_version="1.2.4")

    # When the regex pattern does not match the file contents, apply_bumps should raise
    try:
        vbg.apply_bumps([outcome], dry_run=False)
    except RuntimeError:
        # Expected path: pattern did not match and apply_bumps signaled an error
        return

    # If no exception was raised, the behavior is incorrect for this test case
    assert False, "apply_bumps did not raise RuntimeError when pattern failed to match"


def test_analyze_rule_requires_patch_when_pr_is_lower(monkeypatch) -> None:
    rule = vbg.RULES[1]
    changed = ["src/em/GameStatus.py"]

    monkeypatch.setattr(
        vbg,
        "version_at_ref",
        lambda ref, file_path, pattern: "1.5.2" if ref == "base" else "1.5.1",
    )

    outcome = vbg.analyze_rule(rule, changed, "base", "head")

    assert outcome.requires_bump is True
    assert outcome.target_version == "1.5.3"
