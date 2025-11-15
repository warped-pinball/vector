"""Shared helpers for the build & release workflow."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Dict, Any

TARGET_VERSION_PATTERN = r"SystemVersion\s*=\s*\"([^\"]+)\""
VECTOR_VERSION_PATTERN = r"VectorVersion\s*=\s*\"([^\"]+)\""


@dataclass
class DetermineResult:
    version: str
    target_versions: Dict[str, str]
    release_files: str
    should_sign: bool
    should_release: bool


def load_targets(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text())


def _extract_version(path: Path, pattern: str) -> str:
    text = path.read_text()
    match = re.search(pattern, text)
    if not match:
        raise RuntimeError(f"Unable to find version in {path}")
    return match.group(1)


def determine_versions(
    targets: Iterable[Dict[str, Any]],
    *,
    event_name: str,
    run_number: str,
    pr_number: str,
    shared_state_path: Path,
) -> DetermineResult:
    base_version = _extract_version(shared_state_path, VECTOR_VERSION_PATTERN)
    target_base_versions = {
        target["id"]: _extract_version(Path(target["config_path"]), TARGET_VERSION_PATTERN)
        for target in targets
    }

    if event_name == "pull_request":
        suffix = f"-dev{pr_number}" if pr_number else "-dev"
        should_sign = should_release = False
    elif event_name == "push":
        suffix = f"-beta{run_number}" if run_number else "-beta"
        should_sign = should_release = True
    else:
        suffix = ""
        should_sign = should_release = True

    version = f"{base_version}{suffix}"
    target_versions = {key: f"{value}{suffix}" for key, value in target_base_versions.items()}
    release_files = "\n".join(target["output"] for target in targets)

    return DetermineResult(
        version=version,
        target_versions=target_versions,
        release_files=release_files,
        should_sign=should_sign,
        should_release=should_release,
    )


def _replace_pattern(path: Path, pattern: str, replacement: str) -> None:
    content = path.read_text()
    new_content = re.sub(pattern, replacement, content)
    if content == new_content:
        if replacement in content:
            return
        raise RuntimeError(f"Failed to update version in {path}")
    path.write_text(new_content)


def update_version_files(
    targets: Iterable[Dict[str, Any]],
    *,
    target_versions: Dict[str, str],
    vector_version: str,
    shared_state_path: Path,
) -> None:
    _replace_pattern(
        shared_state_path,
        VECTOR_VERSION_PATTERN,
        f'VectorVersion = "{vector_version}"',
    )
    for target in targets:
        target_version = target_versions[target["id"]]
        _replace_pattern(
            Path(target["config_path"]),
            TARGET_VERSION_PATTERN,
            f'SystemVersion = "{target_version}"',
        )


def _run_command(command: List[str]) -> None:
    subprocess.run(command, check=True)


def build_updates(
    targets: Iterable[Dict[str, Any]],
    *,
    target_versions: Dict[str, str],
    build_dir: str,
    sign: bool,
    private_key: str | None,
) -> None:
    for target in targets:
        target_id = target["id"]
        _run_command(["python", "dev/build.py", "--build-dir", build_dir, "--target_hardware", target_id])

        base_command = [
            "python",
            "dev/build_update.py",
            "--build-dir",
            build_dir,
            "--output",
            target["output"],
            "--version",
            target_versions[target_id],
            "--target_hardware",
            target_id,
        ]

        if sign and private_key:
            with tempfile.NamedTemporaryFile("w", delete=False) as key_file:
                key_file.write(private_key)
                key_path = Path(key_file.name)
            try:
                _run_command(base_command + ["--private-key", str(key_path)])
            finally:
                key_path.unlink(missing_ok=True)
        else:
            _run_command(base_command)


def prepare_pr_artifacts(targets: Iterable[Dict[str, Any]], artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for target in targets:
        source = Path(target["output"])
        if not source.exists():
            continue
        destination = artifact_dir / target["artifact"]
        shutil.copy2(source, destination)


def render_versions_section(
    targets: Iterable[Dict[str, Any]],
    *,
    target_versions: Dict[str, str],
    vector_version: str,
) -> str:
    lines = ["## Versions", f"**Vector**: `{vector_version}`"]
    for target in targets:
        lines.append(f"**{target['label']}**: `{target_versions[target['id']]}`")
    lines.append("<!-- END VERSIONS SECTION -->")
    return "\n".join(lines)


def merge_release_body(existing_body: str, version_section: str) -> str:
    if not existing_body:
        return version_section

    start = existing_body.find("## Versions")
    end_marker = "<!-- END VERSIONS SECTION -->"
    if start != -1:
        end = existing_body.find(end_marker, start)
        if end != -1:
            end += len(end_marker)
            before = existing_body[:start].rstrip()
            after = existing_body[end:].lstrip("\n")
            existing_body = f"{before}\n\n{after}".strip()

    cleaned = existing_body.strip()
    if cleaned:
        return f"{version_section}\n\n{cleaned}"
    return version_section


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    det = subparsers.add_parser("determine-version")
    det.add_argument("--targets", type=Path, required=True)
    det.add_argument("--event-name", required=True)
    det.add_argument("--run-number", default="")
    det.add_argument("--pr-number", default="")
    det.add_argument("--env-file", type=Path, required=True)
    det.add_argument("--output-file", type=Path)
    det.add_argument("--shared-state", type=Path, default=Path("src/common/SharedState.py"))

    upd = subparsers.add_parser("update-versions")
    upd.add_argument("--targets", type=Path, required=True)
    upd.add_argument("--versions-json", required=True)
    upd.add_argument("--vector-version", required=True)
    upd.add_argument("--shared-state", type=Path, default=Path("src/common/SharedState.py"))

    build = subparsers.add_parser("build-updates")
    build.add_argument("--targets", type=Path, required=True)
    build.add_argument("--versions-json", required=True)
    build.add_argument("--build-dir", default="build")
    build.add_argument("--sign", action="store_true")
    build.add_argument("--private-key-env")

    pr_artifacts = subparsers.add_parser("prepare-pr-artifacts")
    pr_artifacts.add_argument("--targets", type=Path, required=True)
    pr_artifacts.add_argument("--artifact-dir", type=Path, default=Path("pr-artifacts"))

    release_body = subparsers.add_parser("render-release-body")
    release_body.add_argument("--targets", type=Path, required=True)
    release_body.add_argument("--versions-json", required=True)
    release_body.add_argument("--vector-version", required=True)
    release_body.add_argument("--existing-body-file", type=Path)
    release_body.add_argument("--output-file", type=Path, required=True)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    targets = load_targets(args.targets)

    if args.command == "determine-version":
        result = determine_versions(
            targets,
            event_name=args.event_name,
            run_number=args.run_number,
            pr_number=args.pr_number,
            shared_state_path=args.shared_state,
        )
        env_path: Path = args.env_file
        with env_path.open("a") as env_file:
            env_file.write(f"VERSION={result.version}\n")
            env_file.write(f"SHOULD_SIGN={'true' if result.should_sign else 'false'}\n")
            env_file.write(f"SHOULD_RELEASE={'true' if result.should_release else 'false'}\n")
            env_file.write("TARGET_VERSIONS<<EOF\n")
            env_file.write(json.dumps(result.target_versions))
            env_file.write("\nEOF\n")
            env_file.write("RELEASE_FILES<<EOF\n")
            env_file.write(result.release_files + "\n")
            env_file.write("EOF\n")
        if args.output_file:
            with args.output_file.open("a") as output:
                output.write(f"version={result.version}\n")

    elif args.command == "update-versions":
        update_version_files(
            targets,
            target_versions=json.loads(args.versions_json),
            vector_version=args.vector_version,
            shared_state_path=args.shared_state,
        )

    elif args.command == "build-updates":
        key = None
        if args.private_key_env:
            key = os.environ.get(args.private_key_env) or None
        build_updates(
            targets,
            target_versions=json.loads(args.versions_json),
            build_dir=args.build_dir,
            sign=args.sign,
            private_key=key,
        )

    elif args.command == "prepare-pr-artifacts":
        prepare_pr_artifacts(targets, args.artifact_dir)

    elif args.command == "render-release-body":
        existing_body = ""
        if args.existing_body_file and args.existing_body_file.exists():
            existing_body = args.existing_body_file.read_text()
        version_section = render_versions_section(
            targets,
            target_versions=json.loads(args.versions_json),
            vector_version=args.vector_version,
        )
        merged = merge_release_body(existing_body, version_section)
        args.output_file.write_text(merged)

    else:
        raise ValueError(f"Unsupported command {args.command}")


if __name__ == "__main__":
    main()
