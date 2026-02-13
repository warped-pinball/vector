"""Tests for JSON config validation."""

from __future__ import annotations

import json
from pathlib import Path

from dev.ci.validate_json_configs import rule_for_path, validate_required_fields


class TestRuleForPath:
    """Test rule matching logic."""

    def test_matches_em_config(self):
        """EM config files match the em-game-config rule."""
        result = rule_for_path("src/em/config/game.json")
        assert result is not None
        assert result["name"] == "em-game-config"

    def test_matches_sys11_config(self):
        """Sys11 config files match the standard-game-config rule."""
        result = rule_for_path("src/sys11/config/game.json")
        assert result is not None
        assert result["name"] == "standard-game-config"

    def test_matches_wpc_config(self):
        """WPC config files match the standard-game-config rule."""
        result = rule_for_path("src/wpc/config/game.json")
        assert result is not None
        assert result["name"] == "standard-game-config"

    def test_matches_data_east_config(self):
        """Data East config files match the standard-game-config rule."""
        result = rule_for_path("src/data_east/config/game.json")
        assert result is not None
        assert result["name"] == "standard-game-config"

    def test_no_match_for_unmatched_path(self):
        """Files not matching any pattern return None."""
        result = rule_for_path("dev/config.json")
        assert result is None

    def test_no_match_for_non_config_json(self):
        """JSON files outside config directories don't match."""
        result = rule_for_path("src/sys11/other.json")
        assert result is None


class TestValidateRequiredFields:
    """Test required field validation logic."""

    def test_valid_em_config(self):
        """Valid EM config with all required fields passes."""
        rule = {
            "name": "em-game-config",
            "required": {
                "GameInfo": ["GameName", "System"],
            },
        }
        payload = {"GameInfo": {"GameName": "Test Game", "System": "EM"}}
        errors = validate_required_fields("test.json", payload, rule)
        assert errors == []

    def test_valid_standard_config(self):
        """Valid standard config with all required fields passes."""
        rule = {
            "name": "standard-game-config",
            "required": {
                "GameInfo": ["GameName", "System"],
                "Memory": ["Start", "Length", "NvStart", "NvLength"],
                "BallInPlay": ["Type"],
                "DisplayMessage": ["Type"],
                "Adjustments": ["Type"],
                "HighScores": ["Type"],
            },
        }
        payload = {
            "GameInfo": {"GameName": "Test", "System": "Sys11"},
            "Memory": {"Start": 0, "Length": 100, "NvStart": 0, "NvLength": 50},
            "BallInPlay": {"Type": "address"},
            "DisplayMessage": {"Type": "address"},
            "Adjustments": {"Type": "address"},
            "HighScores": {"Type": "address"},
        }
        errors = validate_required_fields("test.json", payload, rule)
        assert errors == []

    def test_missing_top_level_object(self):
        """Missing top-level required object is detected."""
        rule = {
            "name": "test-rule",
            "required": {
                "GameInfo": ["GameName"],
            },
        }
        payload = {}
        errors = validate_required_fields("test.json", payload, rule)
        assert len(errors) == 1
        assert "missing required object 'GameInfo'" in errors[0]

    def test_non_dict_top_level_object(self):
        """Top-level object that is not a dict is detected."""
        rule = {
            "name": "test-rule",
            "required": {
                "GameInfo": ["GameName"],
            },
        }
        payload = {"GameInfo": "not a dict"}
        errors = validate_required_fields("test.json", payload, rule)
        assert len(errors) == 1
        assert "missing required object 'GameInfo'" in errors[0]

    def test_missing_nested_field(self):
        """Missing nested field is detected."""
        rule = {
            "name": "test-rule",
            "required": {
                "GameInfo": ["GameName", "System"],
            },
        }
        payload = {"GameInfo": {"GameName": "Test"}}
        errors = validate_required_fields("test.json", payload, rule)
        assert len(errors) == 1
        assert "missing required field 'GameInfo.System'" in errors[0]

    def test_multiple_missing_fields(self):
        """Multiple missing fields are all reported."""
        rule = {
            "name": "test-rule",
            "required": {
                "GameInfo": ["GameName", "System"],
                "Memory": ["Start", "Length"],
            },
        }
        payload = {
            "GameInfo": {"GameName": "Test"},
            "Memory": {"Start": 0},
        }
        errors = validate_required_fields("test.json", payload, rule)
        assert len(errors) == 2
        assert any("GameInfo.System" in e for e in errors)
        assert any("Memory.Length" in e for e in errors)

    def test_empty_required_nested_list(self):
        """Top-level object with no required nested fields is valid."""
        rule = {
            "name": "test-rule",
            "required": {
                "GameInfo": [],
            },
        }
        payload = {"GameInfo": {}}
        errors = validate_required_fields("test.json", payload, rule)
        assert errors == []


class TestEndToEnd:
    """Integration tests for the full validation flow."""

    def test_malformed_json_is_caught(self, tmp_path):
        """Malformed JSON files are detected and reported."""
        from dev.ci.validate_json_configs import main

        # Create a temporary git repository with a malformed JSON file
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        json_file = repo_dir / "config.json"
        json_file.write_text("{invalid json", encoding="utf-8")

        # Mock tracked_json_files to return our test file
        import dev.ci.validate_json_configs as validator

        original_tracked = validator.tracked_json_files
        original_root = validator.REPO_ROOT

        try:
            validator.REPO_ROOT = repo_dir
            validator.tracked_json_files = lambda: [Path("config.json")]

            exit_code = main()
            assert exit_code == 1
        finally:
            validator.tracked_json_files = original_tracked
            validator.REPO_ROOT = original_root

    def test_non_object_top_level_is_caught(self, tmp_path):
        """Non-object top-level JSON values are detected."""
        from dev.ci.validate_json_configs import main

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        config_dir = repo_dir / "src" / "em" / "config"
        config_dir.mkdir(parents=True)
        json_file = config_dir / "game.json"
        json_file.write_text("[]", encoding="utf-8")

        import dev.ci.validate_json_configs as validator

        original_tracked = validator.tracked_json_files
        original_root = validator.REPO_ROOT

        try:
            validator.REPO_ROOT = repo_dir
            validator.tracked_json_files = lambda: [Path("src/em/config/game.json")]

            exit_code = main()
            assert exit_code == 1
        finally:
            validator.tracked_json_files = original_tracked
            validator.REPO_ROOT = original_root

    def test_valid_configs_pass(self, tmp_path):
        """Valid JSON configs pass validation."""
        from dev.ci.validate_json_configs import main

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        config_dir = repo_dir / "src" / "em" / "config"
        config_dir.mkdir(parents=True)
        json_file = config_dir / "game.json"

        valid_config = {"GameInfo": {"GameName": "Test Game", "System": "EM"}}
        json_file.write_text(json.dumps(valid_config), encoding="utf-8")

        import dev.ci.validate_json_configs as validator

        original_tracked = validator.tracked_json_files
        original_root = validator.REPO_ROOT

        try:
            validator.REPO_ROOT = repo_dir
            validator.tracked_json_files = lambda: [Path("src/em/config/game.json")]

            exit_code = main()
            assert exit_code == 0
        finally:
            validator.tracked_json_files = original_tracked
            validator.REPO_ROOT = original_root

    def test_unmatched_paths_are_skipped(self, tmp_path):
        """JSON files that don't match any rule are skipped without error."""
        from dev.ci.validate_json_configs import main

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        json_file = repo_dir / "other.json"
        json_file.write_text("{}", encoding="utf-8")

        import dev.ci.validate_json_configs as validator

        original_tracked = validator.tracked_json_files
        original_root = validator.REPO_ROOT

        try:
            validator.REPO_ROOT = repo_dir
            validator.tracked_json_files = lambda: [Path("other.json")]

            exit_code = main()
            assert exit_code == 0
        finally:
            validator.tracked_json_files = original_tracked
            validator.REPO_ROOT = original_root
