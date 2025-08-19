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

Run the `sync.py` script from the repository root. Pass the target hardware (`sys11`, `wpc`, `em`, or `auto`) as the first argument and optionally the Pico serial port as the second argument.

```bash
python dev/sync.py sys11 /dev/ttyACM0
```

The script builds the project, wipes the Pico, copies the files and connects to the REPL.

To automatically detect and flash all connected boards, run:

```bash
python dev/sync.py auto
```

Each board is identified, firmware for each hardware platform is built once,
and all boards are flashed in parallel. Build artifacts are always written to
`build/<hardware>` so individual builds do not interfere with one another.
When more than one board is flashed, build and flash logs are suppressed and
progress is reported as boards complete (e.g., `2 of 3 boards complete`).

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

Save the file with your values before running `sync.py`.

## Building Update Packages

To generate an over‑the‑air update file run:

```bash
python dev/build_update.py --version 1.2.3 --target_hardware sys11
```
The script packages files from `build/sys11` (or the corresponding hardware subdirectory)
and writes `update.json` to the repository root. Use `--build-dir` to override the
source directory if needed.
