#!/bin/bash

# Constants
PICO_PORT="/dev/ttyACM0"  # Adjust this if your Pico is connected to a different port
GIT_FILE="git_hash.txt"   # The name of the file to store the commit hash on the board
SOURCE_DIR="src"          # Define the folder in the repo to be mapped to Pico's root

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

# Main sync function, handling file upload, deletion, and error checking
sync_files() {
    local dry_run=$1
    local force_sync=$2

    # Get the commit hash currently stored on the Pico
    STORED_HASH=$(get_git_hash_from_pico)
    CURRENT_HASH=$(git rev-parse HEAD)

    # If not forcing and the hashes match, skip syncing
    if [[ "$force_sync" -ne 1 && "$STORED_HASH" == "$CURRENT_HASH" ]]; then
        echo "No changes to sync; Pico is already up-to-date with commit $CURRENT_HASH."
        return
    fi

    # Get list of changed files based on Git diff, scoped to SOURCE_DIR
    CHANGED_FILES=$(git diff --name-status "$STORED_HASH" "$CURRENT_HASH" -- "$SOURCE_DIR")

    # Track if there are changes to process
    files_processed=0

    # Process each file for upload or deletion
    while IFS= read -r line; do
        FILE_STATUS=$(echo "$line" | awk '{print $1}')
        FILE_PATH=$(echo "$line" | awk '{print $2}')
        PICO_FILE=$(echo "$FILE_PATH" | sed "s|^$SOURCE_DIR/||")

        if [ "$FILE_STATUS" == "D" ]; then
            # File was deleted
            echo "Deleting /$PICO_FILE on Pico"
            if [ "$dry_run" -ne 1 ]; then
                mpremote connect "$PICO_PORT" fs rm :/"$PICO_FILE" > /dev/null 2>&1 || echo "Warning: Failed to delete $PICO_FILE"
            fi
        else
            # File was modified or added
            echo "Uploading $FILE_PATH as /$PICO_FILE on Pico"
            if [ "$dry_run" -ne 1 ]; then
                mpremote connect "$PICO_PORT" fs cp "$FILE_PATH" :/"$PICO_FILE" > /dev/null 2>&1 || echo "Warning: Failed to upload $PICO_FILE"
            fi
        fi
        ((files_processed++))
    done <<< "$CHANGED_FILES"

    # If no files were processed, notify the user
    if [ "$files_processed" -eq 0 ]; then
        echo "No files to sync."
        return
    fi

    # Update commit hash on the Pico if not a dry run
    if [ "$dry_run" -ne 1 ]; then
        upload_git_hash
    fi
}

# Full sync function to upload all files in SOURCE_DIR to the Pico and remove extra files
full_sync() {
    echo "Performing full sync of $SOURCE_DIR to Pico's root directory..."
    
    # Upload all files in SOURCE_DIR to Pico
    for file in $(find "$SOURCE_DIR" -type f); do
        PICO_FILE=$(echo "$file" | sed "s|^$SOURCE_DIR/||")
        echo "Uploading $file as /$PICO_FILE"
        mpremote connect "$PICO_PORT" fs cp "$file" :/"$PICO_FILE" > /dev/null 2>&1 || echo "Warning: Failed to upload $PICO_FILE"
    done

    # Remove files on Pico that are not in SOURCE_DIR
    REMOTE_FILES=$(mpremote connect "$PICO_PORT" fs ls /)
    for REMOTE_FILE in $REMOTE_FILES; do
        # If the file is not in SOURCE_DIR, remove it
        if [[ ! "$REMOTE_FILE" =~ ^(git_hash.txt|.*\.(py|txt|other-extensions))$ && -e "$SOURCE_DIR/$REMOTE_FILE" ]]; then
            echo "Removing $REMOTE_FILE from Pico"
            mpremote connect "$PICO_PORT" fs rm :/"$REMOTE_FILE" > /dev/null 2>&1 || echo "Warning: Failed to delete $REMOTE_FILE"
        fi
    done

    # Update commit hash on the Pico
    upload_git_hash
}

# Main script logic
main() {
    case "$1" in
        sync)
            echo "Starting sync..."
            sync_files 0 0  # No dry run, no force
            ;;
        dry-run)
            echo "Starting dry run..."
            sync_files 1 0  # Dry run enabled, no force
            ;;
        full-sync)
            echo "Starting full sync..."
            full_sync       # Full sync ignores commit hash
            ;;
        *)
            echo "Usage: $0 {sync|dry-run|full-sync}"
            exit 1
            ;;
    esac
}

# Run the main function with provided arguments
main "$@"
