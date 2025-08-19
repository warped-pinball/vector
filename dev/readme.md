# Development Setup

These scripts build and deploy Vector to a Raspberry Pi Pico.

## Environment

Vector requires Python 3 and the `mpy-cross` and `mpremote` tools.

### Using `venv`

```bash
python3 -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (Git Bash)
source .venv/Scripts/activate
pip install -r dev/requirements.txt
pre-commit install
```

### Using Conda

```bash
conda create -n vector python=3
conda activate vector
pip install -r dev/requirements.txt
pre-commit install
```

## Build and Flash

Run the `sync.sh` script from the repository root. Pass the target hardware (`sys11` or `wpc`) as the first argument and optionally the Pico serial port as the second argument.

```bash
./dev/sync.sh sys11 /dev/ttyACM0
```

The script builds the project, wipes the Pico, copies the files and connects to the REPL.

To automatically detect and flash all connected boards, run:

```bash
./dev/sync.sh auto
```

Each board is identified, firmware for each hardware platform is built once,
and all boards are flashed in parallel.

## Automatic Configuration

Create a `dev/config.json` file so the sync script can configure Wi‑Fi and game settings automatically:

```json
{
  "ssid": "Your WiFi SSID",
  "password": "Your WiFi Password",
  "gamename": "GenericSystem11",
  "Gpassword": ""
}
```

Save the file with your values before running `sync.sh`.

## Building Update Packages

To generate an over‑the‑air update file run:

```bash
python dev/build_update.py --version 1.2.3 --target_hardware sys11
```

This creates `update.json` in the repository root.
