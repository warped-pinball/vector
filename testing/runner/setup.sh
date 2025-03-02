#!/bin/bash

# Directory for the GitHub Actions runner
RUNNER_DIR="/home/pi/actions-runner"
CONFIG_FILE="/home/pi/runner-config.json"

# Ensure we're running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root. Please use 'sudo'."
    exit 1
fi

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

# Function to install the GitHub runner
install_runner() {
    echo "Installing GitHub Actions runner..."

    # Make sure jq is installed
    apt-get update && apt-get install -y jq

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

    # Configure the runner
    ./config.sh --unattended --url "$URL" --token "$TOKEN" --labels "$LABELS"

    # Create systemd service
    cat > /etc/systemd/system/actions-runner.service << EOF
[Unit]
Description=GitHub Actions Runner
After=network.target

[Service]
ExecStart=$RUNNER_DIR/run.sh
User=pi
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
collect_config
setup_wifi
install_runner

echo "Setup complete! The GitHub Actions runner will start automatically on boot."
echo "You can check its status with: sudo systemctl status actions-runner"

# Reboot to apply changes
echo "Rebooting in 10 seconds..."
sleep 10
reboot
