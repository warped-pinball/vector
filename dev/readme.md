# Development Setup

These scripts build and deploy Vector to a Raspberry Pi Pico.

## Environment

1. Install **Python 3.11** and ensure `mpy-cross` and `mpremote` are available.
2. Create a virtual environment (you can use `venv` or Conda):

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r dev/requirements.txt
   pre-commit install
   ```

## Build and Flash

Run the `sync.sh` script from the repository root. Pass the target hardware (`sys11` or `wpc`) as the first argument and optionally the Pico serial port as the second argument.

```bash
./dev/sync.sh sys11 /dev/ttyACM0
```

The script will build the project, wipe the Pico, copy the files and connect to the REPL.

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
