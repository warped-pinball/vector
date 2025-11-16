from __future__ import annotations

import json
import sys
from pathlib import Path

from dev.ci import workflow_helpers as wh


def write_file(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def build_targets(tmp_path: Path) -> list[dict[str, str]]:
    shared = tmp_path / "SharedState.py"
    write_file(shared, 'VectorVersion = "1.2.3"')

    target_file = tmp_path / "target.py"
    write_file(target_file, 'SystemVersion = "4.5.6"')

    return [
        {
            "id": "sys11",
            "label": "Sys11",
            "config_path": str(target_file),
            "output": "update.json",
            "artifact": "sys11-update.json",
            "raw_filename": "sys11-update.json",
        }
    ], shared


def test_determine_versions_adds_suffix(tmp_path: Path) -> None:
    targets, shared_state = build_targets(tmp_path)

    result = wh.determine_versions(
        targets,
        event_name="pull_request",
        run_number="7",
        pr_number="42",
        shared_state_path=shared_state,
    )

    assert result.version.endswith("-dev42")
    assert result.target_versions["sys11"].endswith("-dev42")
    assert result.should_release is False
    assert result.should_sign is False


def test_update_version_files_rewrites_sources(tmp_path: Path) -> None:
    targets, shared_state = build_targets(tmp_path)
    result = {
        "sys11": "9.9.9-dev",
    }

    wh.update_version_files(
        targets,
        target_versions=result,
        vector_version="2.0.0-dev",
        shared_state_path=shared_state,
    )

    assert '"2.0.0-dev"' in shared_state.read_text()
    assert '"9.9.9-dev"' in Path(targets[0]["config_path"]).read_text()


def test_merge_release_body_replaces_existing_versions(tmp_path: Path) -> None:
    targets, _ = build_targets(tmp_path)
    versions_json = json.dumps({"sys11": "1.2.3"})

    version_section = wh.render_versions_section(
        targets,
        target_versions=json.loads(versions_json),
        vector_version="3.3.3",
    )

    existing = """## Versions\nold\n<!-- END VERSIONS SECTION -->\n\nOther notes"""
    merged = wh.merge_release_body(existing, version_section)

    assert "old" not in merged
    assert "Other notes" in merged
    assert merged.startswith("## Versions")


def test_pr_raw_artifact_metadata_prefers_raw_name(tmp_path: Path) -> None:
    targets, _ = build_targets(tmp_path)
    metadata = wh.pr_raw_artifact_metadata(targets)

    assert metadata == [
        {
            "label": "Sys11",
            "source": "update.json",
            "filename": "sys11-update.json",
        }
    ]


def test_emit_output_generates_delimiter_and_appends_newline(tmp_path: Path) -> None:
    output_file = tmp_path / "gout.txt"

    delimiter = wh.emit_output("body", "content", output_file)

    lines = output_file.read_text().splitlines()
    assert lines[0] == f"body<<{delimiter}"
    assert lines[1] == "content"
    assert lines[2] == delimiter


def test_emit_output_respects_custom_delimiter(tmp_path: Path) -> None:
    output_file = tmp_path / "gout.txt"

    wh.emit_output("body", "value\n", output_file, delimiter="CUSTOM")

    assert output_file.read_text() == "body<<CUSTOM\nvalue\nCUSTOM\n"


def test_main_emit_output_skips_targets(monkeypatch, tmp_path: Path) -> None:
    value_file = tmp_path / "value.txt"
    value_file.write_text("value")
    output_file = tmp_path / "out.txt"

    def fail_load_targets(path):  # pragma: no cover - defensive
        raise AssertionError("load_targets should not be called")

    monkeypatch.setattr(wh, "load_targets", fail_load_targets)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workflow_helpers.py",
            "emit-output",
            "--name",
            "body",
            "--value-file",
            str(value_file),
            "--output-file",
            str(output_file),
            "--delimiter",
            "DELIM",
        ],
    )

    wh.main()

    assert output_file.read_text() == "body<<DELIM\nvalue\nDELIM\n"
