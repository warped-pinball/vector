# steps we need to take:
# "build" project to temp dir
    # minify html, css, & js
    # compile micropython to byte code

# calculate hashes for each file and put into an index
# mount the computer dir to the pico
# copy micro python program onto board
    # walk all files (except those in /remote), and calculate their hash
    # if the hash is different for the path, copy the corresponding file from mount
    # if path isn't in list of hashes, delete it
    # if a hash is in the index with no corresponding file, copy it over








#!/bin/bash

# Constants
PICO_PORT="/dev/ttyACM0"
SOURCE_PATH="$(pwd)/../src"  # Adjust as needed
MOUNT_POINT="/mnt/pico"

# Create the mount point if it doesn't exist
mkdir -p "$MOUNT_POINT"

# Function to sync changed files based on git diff
sync_changed_files() {
    local dry_run=$1
    echo "Syncing changed files in '$SOURCE_PATH' to Pico..."

    # Get the list of changed files
    local changed_files=$(git diff --name-only HEAD~1 HEAD -- "$SOURCE_PATH" | sed "s|^$SOURCE_PATH/||")
    if [[ -z "$changed_files" ]]; then
        echo "No files changed in the last commit."
        return
    fi

    # Process each changed file
    for file in $changed_files; do
        if [[ -f "$SOURCE_PATH/$file" ]]; then
            if [[ "$dry_run" -eq 1 ]]; then
                echo "Dry run: Would upload '$SOURCE_PATH/$file' to '/$file' on Pico."
            else
                echo "Uploading '$SOURCE_PATH/$file' to '/$file' on Pico..."
                mpremote connect "$PICO_PORT" fs put "$SOURCE_PATH/$file" "/$file"
                if [[ $? -ne 0 ]]; then
                    echo "Warning: Failed to upload '$SOURCE_PATH/$file'."
                fi
            fi
        else
            echo "File '$SOURCE_PATH/$file' does not exist."
        fi
    done

    # Update the commit hash on the Pico
    upload_git_hash
}

# Function to perform a full sync of the src directory
full_sync() {
    local dry_run=$1
    echo "Performing full sync of '$SOURCE_PATH' to Pico's root directory..."

    if [[ "$dry_run" -eq 1 ]]; then
        echo "Dry run: Would wipe the Pico and copy '$SOURCE_PATH' recursively."
    else
        # Wipe the Pico filesystem by mounting
        echo "Mounting Pico filesystem..."
        mpremote mount "$PICO_PORT" "$MOUNT_POINT" || {
            echo "Error: Failed to mount Pico filesystem."
            return 1
        }

        # Copy the source directory to Pico
        echo "Copying '$SOURCE_PATH' to Pico..."
        cp -r "$SOURCE_PATH/." "$MOUNT_POINT/"  # Use recursive copy to the mount point
        if [[ $? -ne 0 ]]; then
            echo "Warning: Failed to copy files to Pico."
        else
            echo "Successfully copied '$SOURCE_PATH' to Pico."
        fi

        # Unmount the Pico filesystem after the operation
        mpremote umount "$MOUNT_POINT"
        echo "Unmounted Pico filesystem."
    fi
}

# Function to upload the current git hash to the Pico
upload_git_hash() {
    local hash=$(git rev-parse HEAD)
    echo "Updating Pico commit hash to: $hash"
    echo "$hash" | mpremote connect "$PICO_PORT" fs put - "/git_hash.txt"
}

# Main script
case $1 in
    --full-sync)
        full_sync 0  # 0 means no dry run
        ;;
    --dry-run)
        echo "Dry run: Sync operations will not be performed."
        sync_changed_files 1  # 1 means dry run
        ;;
    *)
        echo "Usage: $0 [--full-sync|--dry-run]"
        exit 1
        ;;
esac
