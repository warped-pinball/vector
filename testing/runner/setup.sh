#!/bin/bash

# Run this script on a Raspberry Pi Zero W to set up a GitHub Actions runner
# This seems to work on the seconrd try but not the first


# Directory for the GitHub Actions runner
RUNNER_DIR="/home/pi/actions-runner"
CONFIG_FILE="/home/pi/runner-config.json"

# Ensure we're running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root. Please use 'sudo'."
    exit 1
fi

# Make sure jq is installed first since we use it throughout the script
echo "Installing dependencies..."
apt-get update && apt-get install -y jq curl tar

# Function to check for existing config
check_existing_config() {
    if [ -f "$CONFIG_FILE" ]; then
        echo "Existing configuration found:"

        # Display existing config (masking sensitive data)
        GITHUB_URL=$(jq -r '.github.url // "Not set"' "$CONFIG_FILE")
        GITHUB_LABELS=$(jq -r '.github.labels // "Not set"' "$CONFIG_FILE")
        WIFI_SSID=$(jq -r '.wifi.ssid // "Not set"' "$CONFIG_FILE")

        echo "GitHub URL: $GITHUB_URL"
        echo "GitHub Labels: $GITHUB_LABELS"
        echo "WiFi SSID: $WIFI_SSID"
        echo "Token and passwords are stored but not displayed"

        echo
        read -p "Do you want to use this existing configuration? (y/n): " use_existing

        if [[ "$use_existing" =~ ^[Yy] ]]; then
            return 0  # Use existing config
        fi
    fi

    return 1  # Need to collect new config
}

# Function to collect configuration
collect_config() {
    echo "GitHub Actions Runner Setup"
    echo "==========================="

    # Ask for GitHub token
    echo "Please provide the token for the runner"
    echo "You can get it from the repository settings -> Actions -> New Runner within the configuration script"
    echo "https://github.com/warped-pinball/vector/settings/actions/runners/new?arch=arm64"
    read -s token
    echo

    # Ask for WiFi details
    echo "Please enter your WiFi SSID:"
    read wifi_ssid
    echo

    echo "Please enter your WiFi password:"
    read -s wifi_password
    echo

    # Create JSON config
    cat > "$CONFIG_FILE" << EOF
{
    "github": {
        "url": "https://github.com/warped-pinball/vector",
        "token": "$token",
        "labels": "pizero,hardware"
    },
    "wifi": {
        "ssid": "$wifi_ssid",
        "password": "$wifi_password"
    }
}
EOF

    chmod 600 "$CONFIG_FILE"  # Secure the config file
    echo "Configuration saved to $CONFIG_FILE"
}

# Function to verify WiFi config is saved (but not apply it)
verify_wifi_config() {
    echo "Verifying WiFi configuration..."

    # Get WiFi details from config
    WIFI_SSID=$(jq -r '.wifi.ssid' "$CONFIG_FILE")
    WIFI_PASS=$(jq -r '.wifi.password' "$CONFIG_FILE")

}

# Function to install the GitHub runner
install_runner() {
    echo "Installing GitHub Actions runner..."


    # Create runner directory
    mkdir -p "$RUNNER_DIR"
    cd "$RUNNER_DIR" || exit

    # Download the runner
    curl -o actions-runner-linux-arm64-2.322.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-linux-arm64-2.322.0.tar.gz

    # Extract the runner
    tar xzf ./actions-runner-linux-arm64-2.322.0.tar.gz

    # Get token from config
    TOKEN=$(jq -r '.github.token' "$CONFIG_FILE")
    URL=$(jq -r '.github.url' "$CONFIG_FILE")
    LABELS=$(jq -r '.github.labels' "$CONFIG_FILE")

    # Determine which user to use
    if id -u pi &>/dev/null; then
        RUNNER_USER="pi"
    elif [ -n "$SUDO_USER" ]; then
        RUNNER_USER="$SUDO_USER"
    else
        RUNNER_USER="pi"  # Default to pi if no suitable user found
    fi

    # Set appropriate ownership
    chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_DIR"

    # Configure the runner
    echo "Registering runner with GitHub..."
    cd "$RUNNER_DIR"
    sudo -u "$RUNNER_USER" ./config.sh --unattended \
        --url "$URL" \
        --token "$TOKEN" \
        --labels "$LABELS" \
        --name "$(hostname)" \
        --work "_work"

    echo "Runner configured successfully!"

    # Create systemd service
    cat > /etc/systemd/system/actions-runner.service << EOF
[Unit]
Description=GitHub Actions Runner
After=network.target

[Service]
ExecStart=$RUNNER_DIR/run.sh
User=$RUNNER_USER
WorkingDirectory=$RUNNER_DIR
KillMode=process
KillSignal=SIGTERM
TimeoutStopSec=5min
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    # Enable and start the service
    systemctl daemon-reload
    systemctl enable actions-runner
    systemctl start actions-runner

    echo "GitHub Actions runner installed and configured to start on boot!"
}

# Main execution
if ! check_existing_config; then
    collect_config
fi

verify_wifi_config
install_runner
echo "Setup complete! The GitHub Actions runner will start automatically on boot."
echo "You can check its status with: sudo systemctl status actions-runner"

# Prompt before reboot
read -p "Press Enter to reboot the system, or Ctrl+C to cancel..." confirm

echo "Rebooting now..."
reboot
