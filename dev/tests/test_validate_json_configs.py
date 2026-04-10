"""Tests for JSON config validation."""

from __future__ import annotations

import json
from pathlib import Path

from dev.ci.validate_json_configs import is_linkto_config, rule_for_path, validate_linkto_config, validate_required_fields


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
                "BallInPlay": ["Type"],
                "DisplayMessage": ["Type"],
                "Adjustments": ["Type"],
                "HighScores": ["Type"],
            },
        }
        payload = {
            "GameInfo": {"GameName": "Test", "System": "Sys11"},
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
                "BallInPlay": ["Type"],
            },
        }
        payload = {
            "GameInfo": {"GameName": "Test"},
            "BallInPlay": {},
        }
        errors = validate_required_fields("test.json", payload, rule)
        assert len(errors) == 2
        assert any("GameInfo.System" in e for e in errors)
        assert any("BallInPlay.Type" in e for e in errors)

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

    def test_malformed_json_is_caught(self, tmp_path, monkeypatch):
        """Malformed JSON files are detected and reported."""
        from dev.ci.validate_json_configs import main

        # Create a temporary git repository with a malformed JSON file
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        json_file = repo_dir / "config.json"
        json_file.write_text("{invalid json", encoding="utf-8")

        # Mock tracked_json_files to return our test file
        import dev.ci.validate_json_configs as validator

        monkeypatch.setattr(validator, "REPO_ROOT", repo_dir)
        monkeypatch.setattr(validator, "tracked_json_files", lambda: [Path("config.json")])

        exit_code = main()
        assert exit_code == 1

    def test_non_object_top_level_is_caught(self, tmp_path, monkeypatch):
        """Non-object top-level JSON values are detected."""
        from dev.ci.validate_json_configs import main

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        config_dir = repo_dir / "src" / "em" / "config"
        config_dir.mkdir(parents=True)
        json_file = config_dir / "game.json"
        json_file.write_text("[]", encoding="utf-8")

        import dev.ci.validate_json_configs as validator

        monkeypatch.setattr(validator, "REPO_ROOT", repo_dir)
        monkeypatch.setattr(validator, "tracked_json_files", lambda: [Path("src/em/config/game.json")])

        exit_code = main()
        assert exit_code == 1

    def test_valid_configs_pass(self, tmp_path, monkeypatch):
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

        monkeypatch.setattr(validator, "REPO_ROOT", repo_dir)
        monkeypatch.setattr(validator, "tracked_json_files", lambda: [Path("src/em/config/game.json")])

        exit_code = main()
        assert exit_code == 0

    def test_unmatched_paths_are_skipped(self, tmp_path, monkeypatch):
        """JSON files that don't match any rule are skipped without error."""
        from dev.ci.validate_json_configs import main

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        json_file = repo_dir / "other.json"
        json_file.write_text("{}", encoding="utf-8")

        import dev.ci.validate_json_configs as validator

        monkeypatch.setattr(validator, "REPO_ROOT", repo_dir)
        monkeypatch.setattr(validator, "tracked_json_files", lambda: [Path("other.json")])

        exit_code = main()
        assert exit_code == 0


class TestIsLinkToConfig:
    """Test LinkTo detection logic."""

    def test_detects_linkto_config(self):
        """Config with LinkTo in GameInfo is detected."""
        payload = {"GameInfo": {"GameName": "Test", "LinkTo": "OtherConfig"}}
        assert is_linkto_config(payload) is True

    def test_regular_config_not_linkto(self):
        """Regular config without LinkTo is not detected."""
        payload = {"GameInfo": {"GameName": "Test", "System": "WPC"}}
        assert is_linkto_config(payload) is False

    def test_missing_game_info_not_linkto(self):
        """Config without GameInfo is not detected as LinkTo."""
        payload = {"BallInPlay": {"Type": 0}}
        assert is_linkto_config(payload) is False

    def test_non_dict_game_info_not_linkto(self):
        """Config with non-dict GameInfo is not detected as LinkTo."""
        payload = {"GameInfo": "not a dict"}
        assert is_linkto_config(payload) is False


class TestValidateLinkToConfig:
    """Test LinkTo config validation logic."""

    def test_valid_linkto_with_existing_target(self, tmp_path, monkeypatch):
        """Valid LinkTo config with existing target passes."""
        import dev.ci.validate_json_configs as validator

        repo_dir = tmp_path / "repo"
        config_dir = repo_dir / "src" / "wpc" / "config"
        config_dir.mkdir(parents=True)
        target_file = config_dir / "TargetConfig.json"
        target_file.write_text("{}", encoding="utf-8")

        monkeypatch.setattr(validator, "REPO_ROOT", repo_dir)

        payload = {"GameInfo": {"GameName": "Test", "LinkTo": "TargetConfig"}}
        errors = validate_linkto_config("src/wpc/config/Alias.json", payload)
        assert errors == []

    def test_linkto_missing_target(self, tmp_path, monkeypatch):
        """LinkTo config pointing to non-existent target fails."""
        import dev.ci.validate_json_configs as validator

        repo_dir = tmp_path / "repo"
        config_dir = repo_dir / "src" / "wpc" / "config"
        config_dir.mkdir(parents=True)

        monkeypatch.setattr(validator, "REPO_ROOT", repo_dir)

        payload = {"GameInfo": {"GameName": "Test", "LinkTo": "NonExistent"}}
        errors = validate_linkto_config("src/wpc/config/Alias.json", payload)
        assert len(errors) == 1
        assert "NonExistent" in errors[0]

    def test_linkto_missing_game_name(self, tmp_path, monkeypatch):
        """LinkTo config without GameName fails."""
        import dev.ci.validate_json_configs as validator

        repo_dir = tmp_path / "repo"
        config_dir = repo_dir / "src" / "wpc" / "config"
        config_dir.mkdir(parents=True)
        target_file = config_dir / "TargetConfig.json"
        target_file.write_text("{}", encoding="utf-8")

        monkeypatch.setattr(validator, "REPO_ROOT", repo_dir)

        payload = {"GameInfo": {"LinkTo": "TargetConfig"}}
        errors = validate_linkto_config("src/wpc/config/Alias.json", payload)
        assert len(errors) == 1
        assert "GameName" in errors[0]

    def test_linkto_empty_target(self):
        """LinkTo config with empty target string fails."""
        payload = {"GameInfo": {"GameName": "Test", "LinkTo": ""}}
        errors = validate_linkto_config("src/wpc/config/Alias.json", payload)
        assert len(errors) == 1
        assert "empty" in errors[0]


class TestEndToEndLinkTo:
    """Integration tests for LinkTo configs in the full validation flow."""

    def test_linkto_config_passes_with_valid_target(self, tmp_path, monkeypatch):
        """LinkTo config passes when linked target exists."""
        from dev.ci.validate_json_configs import main

        repo_dir = tmp_path / "repo"
        config_dir = repo_dir / "src" / "wpc" / "config"
        config_dir.mkdir(parents=True)

        # Create the target config
        target = config_dir / "Target_L1.json"
        target_config = {
            "GameInfo": {"GameName": "Target", "System": "WPC"},
            "BallInPlay": {"Type": "address"},
            "DisplayMessage": {"Type": "address"},
            "Adjustments": {"Type": "address"},
            "HighScores": {"Type": "address"},
        }
        target.write_text(json.dumps(target_config), encoding="utf-8")

        # Create the LinkTo alias config
        alias = config_dir / "Alias_L2.json"
        alias_config = {"GameInfo": {"GameName": "Alias", "LinkTo": "Target_L1"}}
        alias.write_text(json.dumps(alias_config), encoding="utf-8")

        import dev.ci.validate_json_configs as validator

        monkeypatch.setattr(validator, "REPO_ROOT", repo_dir)
        monkeypatch.setattr(
            validator,
            "tracked_json_files",
            lambda: [Path("src/wpc/config/Target_L1.json"), Path("src/wpc/config/Alias_L2.json")],
        )

        exit_code = main()
        assert exit_code == 0

    def test_linkto_config_fails_with_missing_target(self, tmp_path, monkeypatch):
        """LinkTo config fails when linked target does not exist."""
        from dev.ci.validate_json_configs import main

        repo_dir = tmp_path / "repo"
        config_dir = repo_dir / "src" / "wpc" / "config"
        config_dir.mkdir(parents=True)

        # Create only the LinkTo alias config (no target)
        alias = config_dir / "Alias_L2.json"
        alias_config = {"GameInfo": {"GameName": "Alias", "LinkTo": "Missing_L1"}}
        alias.write_text(json.dumps(alias_config), encoding="utf-8")

        import dev.ci.validate_json_configs as validator

        monkeypatch.setattr(validator, "REPO_ROOT", repo_dir)
        monkeypatch.setattr(
            validator,
            "tracked_json_files",
            lambda: [Path("src/wpc/config/Alias_L2.json")],
        )

        exit_code = main()
        assert exit_code == 1
