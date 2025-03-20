# Conda Setup Guide

## Installation

### Linux/Raspberry Pi

1. **Download Miniforge Installer**
   Choose `x86_64` for most Linux PCs or `aarch64` for Raspberry Pi:

   `wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh`
   # OR for Raspberry Pi
   `wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh`

2. **Make the Installer Executable**

   `chmod +x Miniforge3-Linux-*.sh`

3. **Run the Installer**

   `./Miniforge3-Linux-*.sh`

4. **Activate Conda**

   `source ~/miniforge3/bin/activate`

5. **Verify Conda Installation**

   `conda --version`


### Windows

1. **Download Miniforge Installer**
   Visit https://github.com/conda-forge/miniforge/releases and download `Miniforge3-Windows-x86_64.exe`.

2. **Run Installer and Add Conda to PATH**
   Follow the setup prompts, ensuring Conda is added to your PATH.

3. **Activate Conda in New Terminals**
   Open a new Command Prompt and run:

   `conda init`

   Restart Command Prompt if needed.

---

## Setup Environment and Install Requirements

1. **Create Environment**
   `conda create -n pico python=3.11`

2. **Activate Environment**
   `conda activate pico`

3. **Install Requirements**
   `pip install -r dev/requirements.txt`

---

## Usage

1. **Build and Deploy to Pico**
   From the root of your repository:

   `./dev/sync.sh`


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

Replace the placeholder values with your actual WiFi SSID, password, and game name. Save this file and use it as needed for your configuration.
