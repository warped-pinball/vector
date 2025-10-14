#! /usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from common import autodetect_pico_port, mpremote_exec, mpremote_run

REPL_RETRY_DELAY = 1
REPL_MAX_RETRIES = 5
BUILD_DIR_DEFAULT = "build"


def autodetect_pico_port_or_exit():
    port = autodetect_pico_port()
    if port:
        return port
    print("Unable to detect Pico port using mpremote. Please specify the correct port manually.")
    sys.exit(1)


def wipe_pico(pico_port):
    """Wipe the Pico filesystem using mpremote fs commands with logging."""
    print("Wiping Pico's filesystem...")
    # List root entries
    ls = mpremote_run("fs", "ls", "/", connect=pico_port, capture_output=True)
    if ls.returncode != 0:
        print("mpremote fs ls failed:")
        if ls.stdout:
            print(ls.stdout)
        if ls.stderr:
            print(ls.stderr)
        sys.exit(1)
    text = ls.stdout or ""
    # Parse entries per-line: mpremote may print sizes/metadata; take last token as name
    entries: list[str] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        token = ln.split()[-1].rstrip("/")
        if token not in (".", ".."):
            entries.append(token)
    if not entries and text:
        # Debug aid if parsing fails entirely
        print("mpremote fs ls raw output:")
        print(text)
    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for e in entries:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    # Remove each entry using a safe per-entry recursive exec, with fs fallbacks
    for name in uniq:
        path = name if name.startswith("/") else f"/{name}"
        print(f" - removing {path}")
        remove_code = "\n".join(
            [
                "import os",
                "def _rm(p):",
                "    try:",
                "        os.remove(p)",
                "        return",
                "    except OSError:",
                "        pass",
                "    try:",
                "        for e in os.listdir(p):",
                "            _rm(p + '/' + e)",
                "        os.rmdir(p)",
                "    except OSError:",
                "        pass",
                f"_rm('{path}')",
            ]
        )
        try:
            res = mpremote_exec(remove_code, connect=pico_port, capture_output=True, timeout=12)
            if res.returncode == 0:
                continue
            else:
                print(f"   exec removal returned {res.returncode}: falling back to fs")
                if res.stdout:
                    print(res.stdout)
                if res.stderr:
                    print(res.stderr)
        except subprocess.TimeoutExpired:
            print("   exec removal timed out; falling back to fs")
        # Fallback attempts: try file rm, then dir rmdir
        rm = mpremote_run("fs", "rm", path, connect=pico_port, capture_output=True)
        if rm.returncode != 0 and not ((rm.stdout or "").find("ENOENT") != -1 or (rm.stderr or "").find("ENOENT") != -1):
            rmdir = mpremote_run("fs", "rmdir", path, connect=pico_port, capture_output=True)
            if rmdir.returncode != 0 and not ((rmdir.stdout or "").find("ENOENT") != -1 or (rmdir.stderr or "").find("ENOENT") != -1):
                print(f"   failed to remove {path} via fs:")
                if rm.stdout or rm.stderr:
                    print("   rm output:")
                    if rm.stdout:
                        print(rm.stdout)
                    if rm.stderr:
                        print(rm.stderr)
                if rmdir.stdout or rmdir.stderr:
                    print("   rmdir output:")
                    if rmdir.stdout:
                        print(rmdir.stdout)
                    if rmdir.stderr:
                        print(rmdir.stderr)
    print("Filesystem wipe complete.")


def copy_files_to_pico(build_dir, pico_port):
    """Copy from build_dir to Pico."""
    print("Copying files to Pico from:", build_dir)
    original_dir = os.getcwd()
    os.chdir(build_dir)
    try:
        result = mpremote_run("fs", "cp", "-r", ".", ":", connect=pico_port)
        if result.returncode != 0:
            print("Error copying files to Pico.")
            sys.exit(1)
    finally:
        os.chdir(original_dir)
    print("Sync complete.")


def restart_pico(pico_port):
    print("Restarting the Pico...")
    result = mpremote_exec("import machine; machine.reset()", connect=pico_port, no_follow=True)
    if result.returncode != 0:
        print("Error restarting the Pico.")
        sys.exit(1)
    print("Pico restarted.")


def wipe_config_data(pico_port):
    print("Wiping config data on Pico...")
    script = "\n".join(
        [
            "import SPI_DataStore as datastore",
            "datastore.blankAll()",
            "import Adjustments",
            "Adjustments.blank_all()",
        ]
    )
    for attempt in range(3):
        time.sleep(REPL_RETRY_DELAY)
        result = mpremote_exec(script, connect=pico_port)
        if result.returncode == 0:
            break
        print(f"Error wiping config on Pico. Retrying... ({attempt + 1})")
    if result.returncode != 0:
        print("Error wiping config on Pico after 3 attempts.")
        sys.exit(1)


def apply_local_config_to_pico(pico_port, config_file="dev/config.json"):
    """Apply a local config file to the Pico's SPI_DataStore."""
    config_path = Path(config_file).resolve()
    if not config_path.exists():
        print("No local config file found at:", config_path)
        return

    print("Applying local configuration to Pico...")
    with open(config_path, "r") as cf:
        local_config = json.load(cf)
    config_script_lines = [
        "import SPI_DataStore as datastore",
        "config = datastore.read_record('configuration')",
    ]
    for key, value in local_config.items():
        config_script_lines.append(f"config['{key}'] = '{value}'")
    config_script_lines.append("datastore.write_record('configuration', config)")

    for attempt in range(3):
        time.sleep(REPL_RETRY_DELAY)
        result = mpremote_exec(";".join(config_script_lines), connect=pico_port)
        if result.returncode == 0:
            print("Configuration updated successfully on Pico.")
            return
        print(f"Error applying configuration to Pico. Retrying... ({attempt + 1})")
    print("Error applying configuration to Pico after 3 attempts.")
    sys.exit(1)


def write_test_data(pico_port, test_data_file="dev/test_data.json"):
    """Write test data to the Pico."""
    test_data_file_path = Path(__file__).parent / "test_data.json"
    if not test_data_file_path.exists():
        print("Test data file not found.")
        return
    with open(test_data_file_path, "r") as f:
        test_data = json.load(f)

    test_data_script = "\n".join(
        # set player names
        [
            "import SPI_DataStore as datastore",
            "import ScoreTrack",
        ]
        + [f'datastore.write_record("names", {json.dumps(record)}, {index})' for index, record in enumerate(test_data["names"])]
        # set leaderboard data
        + [
            "from ScoreTrack import update_leaderboard, update_tournament",
        ]
        # add leaderboard and tournament data
        # + [f"update_leaderboard({json.dumps(record)})" for record in test_data["leaders"]]
        + [f'datastore.write_record("leaders", {json.dumps(record)}, {index})' for index, record in enumerate(test_data["leaders"])]
        + [f"update_tournament({json.dumps(record)})" for record in test_data["tournament"]]
        + [
            'extras = datastore.read_record("extras", 0)',
            f'extras["other"] = {test_data["settings"]["score_capture"]}',
            'datastore.write_record("extras", extras, 0)',
        ]
        # add individual player data
        + [f"ScoreTrack.update_individual_score({json.dumps(record)})" for record in test_data["individual"]]
    )

    for attempt in range(3):
        time.sleep(REPL_RETRY_DELAY)
        result = mpremote_exec(test_data_script, connect=pico_port)
        if result.returncode == 0:
            break
        print(f"Error writing test data to Pico. Retrying... ({attempt + 1})")
    if result.returncode != 0:
        print("Error writing test data to Pico.")
        sys.exit(1)
    print("Test data written successfully to Pico.")


def main():
    # TODO hook up these arguments
    parser = argparse.ArgumentParser(description="Flash an already-built project directory to the Pico.")
    parser.add_argument(
        "build_dir",
        default=BUILD_DIR_DEFAULT,
        nargs="?",
        help="Path to the build directory.",
    )
    parser.add_argument("--env", default="dev", help="Deployment environment (dev, test, prod, etc.)")
    parser.add_argument(
        "--port",
        help="Specify the Pico port manually. If not provided, autodetect is attempted.",
    )
    parser.add_argument("--wipe", action="store_true", help="Wipe Pico filesystem before copying files.")
    parser.add_argument(
        "--wipe-config",
        action="store_true",
        help="Wipe config data on Pico after copying.",
    )
    parser.add_argument(
        "--apply-local-config",
        action="store_true",
        help="Apply local config.json to Pico after copying.",
    )
    parser.add_argument(
        "--test-data",
        action="store_true",
        help="Write test data from test_data.json to Pico.",
    )
    parser.add_argument("--restart", action="store_true", help="Restart Pico after flashing.")
    args = parser.parse_args()

    pico_port = args.port if args.port else autodetect_pico_port_or_exit()

    wipe_pico(pico_port)

    copy_files_to_pico(args.build_dir, pico_port)

    wipe_config_data(pico_port)

    apply_local_config_to_pico(pico_port)

    write_test_data(pico_port)

    restart_pico(pico_port)


if __name__ == "__main__":
    main()
