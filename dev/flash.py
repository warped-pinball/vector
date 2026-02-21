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
    """Wipe the Pico filesystem by running a recursive delete directly on the device."""
    print("Wiping Pico's filesystem...")

    wipe_script = "\n".join(
        [
            "import os",
            "",
            "def _listdir(p):",
            "    try:",
            "        return os.listdir(p)",
            "    except OSError:",
            "        return os.listdir()",
            "",
            "def _rm_tree(p):",
            "    # Try file first",
            "    try:",
            "        os.remove(p)",
            "        return",
            "    except OSError:",
            "        pass",
            "    # Then directory",
            "    try:",
            "        for name in _listdir(p):",
            "            if name in ('.', '..'):",
            "                continue",
            "            _rm_tree(p + '/' + name)",
            "        os.rmdir(p)",
            "    except OSError:",
            "        pass",
            "",
            "for name in _listdir('/'):",
            "    if name in ('.', '..'):",
            "        continue",
            "    _rm_tree('/' + name)",
        ]
    )

    try:
        result = mpremote_exec(wipe_script, connect=pico_port, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        print("Error wiping Pico filesystem: operation timed out.")
        sys.exit(1)

    if result.returncode == 0:
        print("Filesystem wipe complete.")
        return

    print("Error wiping Pico filesystem.")
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    sys.exit(1)


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
        if result.stderr:
            print(result.stderr.strip())
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
        "--write-config",
        nargs="?",
        const="__DEFAULT__",
        metavar="PATH",
        help=(
            "Wipe config on Pico and write configuration from PATH. "
            "If provided with no PATH, uses the default config for the selected build_dir (dev/config.json, or dev/config_sys11.json/dev/config_wpc.json if present)."
        ),
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

    if args.write_config is not None:
        if args.write_config == "__DEFAULT__":
            # Optionally sync a specific config file for that OS if it exists, else default to dev/config.json.
            config_file = "dev/config.json"
            if args.build_dir == "build/sys11" and os.path.isfile("dev/config_sys11.json"):
                config_file = "dev/config_sys11.json"
            elif args.build_dir == "build/wpc" and os.path.isfile("dev/config_wpc.json"):
                config_file = "dev/config_wpc.json"
            elif args.build_dir == "build/em" and os.path.isfile("dev/config_em.json"):
                config_file = "dev/config_em.json"
        else:
            config_file = args.write_config

        if not os.path.isfile(config_file):
            print("Config file not found:", config_file)
            sys.exit(1)

        wipe_config_data(pico_port)
        apply_local_config_to_pico(pico_port, config_file=config_file)

    if args.test_data:
        write_test_data(pico_port)

    restart_pico(pico_port)


if __name__ == "__main__":
    main()
