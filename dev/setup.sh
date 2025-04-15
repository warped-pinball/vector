# Setup python environment
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip


# Install python dependencies
pip install -r requirements.txt

# Install pre-commit hooks
pre-commit install

# Download the latest version of Trench Coat for this OS
# https://github.com/warped-pinball/trench-coat/releases/latest

# Determine OS
OS=$(uname -s | tr '[:upper:]' '[:lower:]')


# Get the latest release info
RELEASE_INFO=$(curl -s https://api.github.com/repos/warped-pinball/trench-coat/releases/latest)

# Find the asset for this OS and architecture
LATEST_URL=$(echo "$RELEASE_INFO" |
             grep -i "browser_download_url.*${OS}.*${ARCH}" |
             head -n 1 |
             cut -d '"' -f 4)

if [ -z "$LATEST_URL" ]; then
    echo "Error: Could not find Trench Coat release for ${OS}-${ARCH}"
    exit 1
fi

# Download the binary
echo "Downloading from $LATEST_URL..."
FILENAME="bin/$(basename "$LATEST_URL")"
curl -L -o "$FILENAME" "$LATEST_URL"

# Make it executable
chmod +x "$FILENAME"

echo "Trench Coat downloaded successfully to $FILENAME"
