#!/usr/bin/env bash
#
# sync.sh
#
# Usage:
#   ./sync.sh [sys11|wpc|em|auto] [port]
#
# Description:
#   1) Build the project for the chosen hardware (defaults to 'dev').
#   2) Flash the board (wipe, copy files, apply config).
#   3) Connect to the board REPL via mpremote.

# --- Configuration ---

SYSTEM="${1:-dev}"     # If user doesn't specify, default to 'dev'
BUILD_DIR="build"           # adjust as necessary
SOURCE_DIR="src"            # adjust as necessary
PORT="${2}"                # optionally define port

if [ "$SYSTEM" = "auto" ]; then
  echo "Detecting connected boards ..."
  BOARDS_JSON=$(python dev/detect_boards.py)
  if [ $? -ne 0 ] || [ -z "$BOARDS_JSON" ]; then
    echo "No boards detected. Aborting."
    exit 1
  fi
  echo "Boards detected: $BOARDS_JSON"
  python - "$BOARDS_JSON" <<'PYTHON'
import json, subprocess, sys
mapping = json.loads(sys.argv[1])
for hardware, ports in mapping.items():
    build_dir = f"build/{hardware}"
    subprocess.check_call([
        "python",
        "dev/build.py",
        "--build-dir",
        build_dir,
        "--source-dir",
        "src",
        "--target_hardware",
        hardware,
    ])
    for port in ports:
        subprocess.check_call([
            "python",
            "dev/flash.py",
            build_dir,
            "--port",
            port,
        ])
PYTHON
  exit $?
fi

# --- 1. Build the project ---
echo "Building project for system=${SYSTEM} ..."
python dev/build.py --build-dir "$BUILD_DIR" --source-dir "$SOURCE_DIR" --target_hardware "$SYSTEM"
if [ $? -ne 0 ]; then
  echo "Build failed. Aborting."
  exit 1
fi

# --- 2. Flash the board ---
echo "Flashing the Pico ..."
# We'll pass the same environment if needed, but flash.py might not need it
# for the basic steps. Adjust if your flash.py script has extra flags.
PORT_PARAM=""
if [ -n "$PORT" ]; then
PORT_PARAM="--port ${PORT}"
fi
python dev/flash.py "$BUILD_DIR" $PORT_PARAM
if [ $? -ne 0 ]; then
  echo "Flashing failed. Aborting."
  exit 1
fi

# --- 3. Connect to REPL ---
echo "Connecting to mpremote REPL ..."
# try to connect to the REPL once every second for 10 seconds
for i in {1..10}; do
  mpremote
  if [ $? -eq 0 ]; then
    break
  fi
  sleep 1
done
