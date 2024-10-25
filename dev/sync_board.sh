#!/bin/bash

# Constants
PICO_PORT="/dev/ttyACM0"  # Adjust this if your Pico is connected to a different port
GIT_FILE="git_hash.txt"   # The name of the file to store the commit hash on the board
SOURCE_DIR="src"          # Define the folder in the repo to be mapped to Pico's root directory

# Get the directory of the currently executing script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_PATH="$SCRIPT_DIR/../$SOURCE_DIR"  # Full path to the source directory

# Helper to retrieve the current Git hash stored on the Pico
get_git_hash_from_pico() {
    TEMP_FILE="pico_$GIT_FILE"
    mpremote connect "$PICO_PORT" fs cp :/"$GIT_FILE" "$TEMP_FILE" > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "No previous commit hash found on the Pico."
        return 1
    fi
    STORED_HASH=$(cat "$TEMP_FILE")
    rm -f "$TEMP_FILE"
    echo "$STORED_HASH"
}

# Helper to update the Git hash on the Pico
upload_git_hash() {
    COMMIT_HASH=$(git rev-parse HEAD)
    echo "$COMMIT_HASH" > "$GIT_FILE"
    mpremote connect "$PICO_PORT" fs cp "$GIT_FILE" :/"$GIT_FILE" > /dev/null 2>&1
    rm -f "$GIT_FILE"
    echo "Updated Pico commit hash to: $COMMIT_HASH"
}

# Sync files based on hash comparison
sync_files() {
    local dry_run=$1

    # Get the commit hash currently stored on the Pico
    STORED_HASH=$(get_git_hash_from_pico)
    CURRENT_HASH=$(git rev-parse HEAD)

    # If the hashes match, skip syncing
    if [[ "$STORED_HASH" == "$CURRENT_HASH" ]]; then
        echo "No changes to sync; Pico is already up-to-date with commit $CURRENT_HASH."
        return
    fi

    # Get list of changed files based on Git diff, scoped to SOURCE_DIR
    CHANGED_FILES=$(git diff --name-status "$STORED_HASH" "$CURRENT_HASH" -- "$SOURCE_PATH")

    # Track if there are changes to process
    files_processed=0

    # Process each file for upload
    while IFS= read -r line; do
        FILE_STATUS=$(echo "$line" | awk '{print $1}')
        FILE_PATH=$(echo "$line" | awk '{print $2}')
        PICO_FILE=$(echo "$FILE_PATH" | sed "s|^$SOURCE_PATH/||")

        if [ "$FILE_STATUS" != "D" ]; then
            if [[ "$dry_run" -eq 1 ]]; then
                echo "Dry run: Would upload $FILE_PATH as /$PICO_FILE"
            else
                echo "Uploading $FILE_PATH as /$PICO_FILE"
                mpremote connect "$PICO_PORT" fs cp "$FILE_PATH" :/"$PICO_FILE" > /dev/null 2>&1 || echo "Warning: Failed to upload $PICO_FILE"
            fi
            ((files_processed++))
        fi
    done <<< "$CHANGED_FILES"

    # If no files were processed, notify the user
    if [ "$files_processed" -eq 0 ]; then
        echo "No files to sync."
    else
        # Update commit hash on the Pico if not a dry run
        if [ "$dry_run" -ne 1 ]; then
            upload_git_hash
        fi
    fi
}

# Full sync function to wipe and copy entire src directory
full_sync() {
    local dry_run=$1
    echo "Performing full sync of $SOURCE_PATH to Pico's root directory..."

    if [[ "$dry_run" -eq 1 ]]; then
        echo "Dry run: Would wipe the Pico and copy $SOURCE_PATH recursively."
    else
        mpremote connect "$PICO_PORT" fs rm -r :/ > /dev/null 2>&1
        echo "Wiped Pico filesystem."
        mpremote connect "$PICO_PORT" fs cp -r "$SOURCE_PATH/" :/ > /dev/null 2>&1 || echo "Warning: Failed to copy files to Pico."
        echo "Copied $SOURCE_PATH to Pico."
        upload_git_hash
    fi
}

# Main script logic
main() {
    local dry_run=0
    local full_sync=0

    # Parse command line options
    while [[ "$#" -gt 0 ]]; do
        case "$1" in
            -f|--full-sync)
                full_sync=1
                ;;
            --dry-run)
                dry_run=1
                ;;
            *)
                echo "Usage: $0 [-f|--full-sync] [--dry-run]"
                exit 1
                ;;
        esac
        shift
    done

    if [[ "$full_sync" -eq 1 ]]; then
        echo "Starting full sync..."
        full_sync "$dry_run"
    else
        echo "Starting sync..."
        sync_files "$dry_run"
    fi
}

# Run the main function with provided arguments
main "$@"
