#!/bin/bash

# Constants
PICO_PORT="/dev/ttyACM0"  # Adjust this if your Pico is connected to a different port
GIT_FILE="git_hash.txt"   # The name of the file to store the commit hash on the board
SOURCE_DIR="src"          # Define the folder in the repo to be mapped to Pico's root

# Function to upload the current Git commit hash to the Pico
upload_git_hash() {
    # Check if the script is run inside a Git repository
    if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
        echo "Error: Not inside a Git repository."
        exit 1
    fi

    # Get the current Git commit hash
    COMMIT_HASH=$(git rev-parse HEAD)
    if [ $? -ne 0 ]; then
        echo "Error: Failed to retrieve Git commit hash."
        exit 1
    fi

    # Create a small text file with just the commit hash
    echo "$COMMIT_HASH" > "$GIT_FILE"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create $GIT_FILE."
        exit 1
    fi

    # Upload the file to the Pico using mpremote
    mpremote connect "$PICO_PORT" fs cp "$GIT_FILE" :/"$GIT_FILE"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to upload $GIT_FILE to Raspberry Pi Pico."
        exit 1
    fi

    echo "Uploaded $GIT_FILE with commit hash: $COMMIT_HASH"
}

# Function to retrieve the Git commit hash from the Pico
get_git_hash_from_pico() {
    # Create a temporary file to store the hash from the board
    TEMP_FILE="pico_$GIT_FILE"

    # Download the git hash file from the Pico
    mpremote connect "$PICO_PORT" fs cp :/"$GIT_FILE" "$TEMP_FILE"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to retrieve $GIT_FILE from Raspberry Pi Pico."
        exit 1
    fi

    # Extract the commit hash from the downloaded file
    STORED_HASH=$(cat "$TEMP_FILE")
    if [ $? -ne 0 ]; then
        echo "Error: Failed to read commit hash from $TEMP_FILE."
        rm -f "$TEMP_FILE"
        exit 1
    fi

    # Clean up the temporary file
    rm -f "$TEMP_FILE"

    echo "Retrieved commit hash from Pico: $STORED_HASH"
}

# Function to list files changed between the current Git commit and the one on the Pico, scoped to the source directory
list_changed_files() {
    # Retrieve the stored hash from the Pico
    get_git_hash_from_pico

    # Get the current Git commit hash
    CURRENT_HASH=$(git rev-parse HEAD)
    if [ $? -ne 0 ]; then
        echo "Error: Failed to retrieve current Git commit hash."
        exit 1
    fi

    # List files changed between the stored hash and the current commit, only within the source directory
    echo "Listing changed files in '$SOURCE_DIR' between commits $STORED_HASH and $CURRENT_HASH:"
    git diff --name-only "$STORED_HASH" "$CURRENT_HASH" -- "$SOURCE_DIR"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to list changed files."
        exit 1
    fi
}

# Main script logic
main() {
    if [ "$1" == "upload" ]; then
        upload_git_hash
    elif [ "$1" == "retrieve" ]; then
        get_git_hash_from_pico
    elif [ "$1" == "list-changed" ]; then
        list_changed_files
    else
        echo "Usage: $0 {upload|retrieve|list-changed}"
        exit 1
    fi
}

# Run the main function with provided arguments
main "$@"
