#! /usr/bin/env python3

import os
import sys
import time
import json
import argparse
import subprocess
from pathlib import Path

REPL_RETRY_DELAY = 1
REPL_MAX_RETRIES = 5
BUILD_DIR_DEFAULT = "build"

def autodetect_pico_port():
    """Auto-detect the Pico port using mpremote. Returns port or exits on failure."""
    try:
        result = subprocess.run("mpremote connect list", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            output = result.stdout.decode().strip()
            if output:
                # first line, first token
                return output.split('\n')[0].split()[0]
        print("Unable to detect Pico port using mpremote. Please specify the correct port manually.")
    except Exception as e:
        print(f"Error detecting Pico port: {e}")
    sys.exit(1)

def wipe_pico(pico_port):
    """Wipe the Pico filesystem."""
    print("Wiping Pico's filesystem...")
    mpython = '\n'.join([
        "import os",
        "def remove(path):",
        "    try:",
        "        os.remove(path)",
        "    except OSError:",
        "        for entry in os.listdir(path):",
        "            remove('/'.join((path, entry)))",
        "        os.rmdir(path)",
        "for entry in os.listdir('/'):",
        "    remove('/' + entry)"
    ])
    cmd = f"mpremote connect {pico_port} exec \"{mpython}\""
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("Error wiping Pico's filesystem.")
        sys.exit(1)

def copy_files_to_pico(build_dir, pico_port):
    """Copy from build_dir to Pico."""
    print("Copying files to Pico from:", build_dir)
    original_dir = os.getcwd()
    os.chdir(build_dir)
    try:
        cmd = f"mpremote connect {pico_port} fs cp -r . :"
        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            print("Error copying files to Pico.")
            sys.exit(1)
    finally:
        os.chdir(original_dir)
    print("Sync complete.")

def restart_pico(pico_port):
    print("Restarting the Pico...")
    cmd = f"mpremote connect {pico_port} exec --no-follow 'import machine; machine.reset()'"
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("Error restarting the Pico.")
        sys.exit(1)
    print("Pico restarted.")

def wipe_config_data(pico_port):
    print("Wiping config data on Pico...")
    script = '\n'.join([
        "import SPI_DataStore as datastore",
        "datastore.blankAll()"
    ])
    cmd = f"mpremote connect {pico_port} exec \"{script}\""
    for attempt in range(3):
        time.sleep(REPL_RETRY_DELAY)
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            break
        print(f"Error wiping config on Pico. Retrying... ({attempt + 1})")
    if result.returncode != 0:
        print("Error wiping config on Pico after 3 attempts.")
        sys.exit(1)

def apply_local_config_to_pico(pico_port, config_file='dev/config.json'):
    """Apply a local config file to the Pico's SPI_DataStore."""
    config_path = Path(config_file).resolve()
    if not config_path.exists():
        print("No local config file found at:", config_path)
        return

    print("Applying local configuration to Pico...")
    with open(config_path, 'r') as cf:
        local_config = json.load(cf)
    config_script_lines = [
        "import SPI_DataStore as datastore",
        "config = datastore.read_record('configuration')",
    ]
    for key, value in local_config.items():
        config_script_lines.append(f"config['{key}'] = '{value}'")
    config_script_lines.append("datastore.write_record('configuration', config)")

    cmd = f"mpremote connect {pico_port} exec \"{';'.join(config_script_lines)}\""
    for attempt in range(3):
        time.sleep(REPL_RETRY_DELAY)
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            print("Configuration updated successfully on Pico.")
            return
        print(f"Error applying configuration to Pico. Retrying... ({attempt + 1})")
    print("Error applying configuration to Pico after 3 attempts.")
    sys.exit(1)

def write_test_data(pico_port, test_data_file='dev/test_data.json'):
    """Write test data to the Pico."""
    data_path = Path(test_data_file).resolve()
    if not data_path.exists():
        print("Test data file not found at:", data_path)
        return

    print("Writing test data to Pico...")
    with open(data_path, 'r') as f:
        test_data = json.load(f)

    script_lines = ["import SPI_DataStore as datastore"]
    # player names
    for idx, record in enumerate(test_data.get("names", [])):
        script_lines.append(f'datastore.write_record("names", {json.dumps(record)}, {idx})')
    # leaderboard
    script_lines.append("from ScoreTrack import update_leaderboard")
    for record in test_data.get("leaders", []):
        script_lines.append(f'update_leaderboard({json.dumps(record)})')
    # turn on tournament mode
    script_lines.append("import SharedState")
    script_lines.append("SharedState.tournamentModeOn = 1")
    for record in test_data.get("tournament", []):
        script_lines.append(f'update_leaderboard({json.dumps(record)})')
    # turn off tournament mode
    script_lines.append("SharedState.tournamentModeOn = 0")
    # set score capture
    script_lines.append('extras = datastore.read_record("extras", 0)')
    script_lines.append(f'extras["other"] = {test_data.get("settings", {}).get("score_capture", {})}')
    script_lines.append('datastore.write_record("extras", extras, 0)')

    cmd = f"mpremote connect {pico_port} exec \"{';'.join(script_lines)}\""
    for attempt in range(3):
        time.sleep(REPL_RETRY_DELAY)
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            print("Test data written successfully to Pico.")
            return
        print(f"Error writing test data to Pico. Retrying... ({attempt + 1})")
    print("Error writing test data to Pico after 3 attempts.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Flash an already-built project directory to the Pico."
    )
    parser.add_argument("build_dir", default=BUILD_DIR_DEFAULT, nargs="?", help="Path to the build directory.")
    parser.add_argument("--env", default="dev", help="Deployment environment (dev, test, prod, etc.)")
    parser.add_argument("--port", help="Specify the Pico port manually. If not provided, autodetect is attempted.")
    parser.add_argument("--wipe", action="store_true", help="Wipe Pico filesystem before copying files.")
    parser.add_argument("--wipe-config", action="store_true", help="Wipe config data on Pico after copying.")
    parser.add_argument("--apply-local-config", action="store_true", help="Apply local config.json to Pico after copying.")
    parser.add_argument("--test-data", action="store_true", help="Write test data from test_data.json to Pico.")
    parser.add_argument("--restart", action="store_true", help="Restart Pico after flashing.")
    args = parser.parse_args()

    pico_port = args.port if args.port else autodetect_pico_port()

    
    wipe_pico(pico_port)

    copy_files_to_pico(args.build_dir, pico_port)

    wipe_config_data(pico_port)

    apply_local_config_to_pico(pico_port)

    write_test_data(pico_port)

    restart_pico(pico_port)


if __name__ == "__main__":
    main()
