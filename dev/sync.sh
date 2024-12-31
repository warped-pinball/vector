#!/usr/bin/env bash
#
# deploy.sh
#
# Usage:
#   ./deploy.sh [dev|beta|prod]
#
# Description:
#   1) Build the project (defaults to 'dev' environment).
#   2) Flash the board (wipe, copy files, apply config).
#   3) Connect to the board REPL via mpremote.

# --- Configuration ---

ENVIRONMENT="${1:-dev}"     # If user doesn't specify, default to 'dev'
BUILD_DIR="build"           # adjust as necessary
SOURCE_DIR="src"            # adjust as necessary

# --- 1. Build the project ---
echo "Building project with environment=${ENVIRONMENT} ..."
python dev/build.py --build-dir "$BUILD_DIR" --source-dir "$SOURCE_DIR" --env "$ENVIRONMENT"
if [ $? -ne 0 ]; then
  echo "Build failed. Aborting."
  exit 1
fi

# --- 2. Flash the board ---
echo "Flashing the Pico ..."
# We'll pass the same environment if needed, but flash.py might not need it 
# for the basic steps. Adjust if your flash.py script has extra flags.
python dev/flash.py "$BUILD_DIR"
if [ $? -ne 0 ]; then
  echo "Flashing failed. Aborting."
  exit 1
fi

# --- 3. Connect to REPL ---
echo "Connecting to mpremote REPL ..."
mpremote
