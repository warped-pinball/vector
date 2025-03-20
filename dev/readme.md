# Conda Setup Guide

## Installation

### Linux/Raspberry Pi

```bash
# Download Miniforge Installer
# For x86_64 (most Linux PCs)
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
# OR for Raspberry Pi (aarch64)
# wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh

# Make the installer executable
chmod +x Miniforge3-Linux-*.sh

# Run the installer
./Miniforge3-Linux-*.sh

# Activate Conda (after installation)
source ~/miniforge3/bin/activate

# Verify installation
conda --version
```

### Windows

1. **Download Miniforge Installer**  
   Visit https://github.com/conda-forge/miniforge/releases and download `Miniforge3-Windows-x86_64.exe`

2. **Run Installer**  
   Follow the setup prompts, ensuring Conda is added to your PATH.

3. **Activate Conda**  
   ```cmd
   conda init
   ```
   Restart Command Prompt after running this command.

## Setup Environment and Install Requirements

```bash
# Create environment
conda create -n pico python=3.11

# Activate environment
conda activate pico

# Install requirements
pip install -r dev/requirements.txt
```

## Usage

**Build and Deploy to Pico:**

```bash
# From the root of your repository
./dev/sync.sh
```

## Automatic Configuration

To automatically configure your vector when flashing, create a JSON file with the following structure:

```json
{
   "ssid": "Your WiFi SSID",
   "password": "Your WiFi Password",
   "gamename": "GenericSystem11",
   "Gpassword": ""
}
```

Replace the placeholder values with your actual WiFi SSID, password, and game name.
