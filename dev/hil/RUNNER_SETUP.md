# HIL Bench — Pi Runner Setup

Minimal setup to make a Raspberry Pi with Vector boards attached run GitHub Actions jobs.
Assumes the Pi is assembled, boards are on a powered USB hub, arm64 userland, and the boards
sit on the same VLAN as the Pi (so there is no routing or firewall setup to do here).

Board detection and flashing use the repo's existing dev pipeline (`dev/detect_boards.py`,
`dev/sync.py`), so there is nothing bench-specific to configure.

```bash
# --- system packages -------------------------------------------------------
sudo apt update
sudo apt install -y git python3-venv curl
```

```bash
# --- repo + dev pipeline ---------------------------------------------------
git clone https://github.com/warped-pinball/vector.git ~/vector
python3 -m venv ~/vector/.venv
~/vector/.venv/bin/pip install -r ~/vector/dev/requirements.txt

# confirm the boards enumerate and identify themselves
cd ~/vector && .venv/bin/python dev/detect_boards.py
```

That last command should print something like
`{"sys11": ["/dev/ttyACM0"], "wpc": ["/dev/ttyACM1"], "data_east": ["/dev/ttyACM2"]}`.
If it does, the hardware side is done.

```bash
# --- actions runner --------------------------------------------------------
mkdir -p ~/actions-runner && cd ~/actions-runner

curl -fSLo runner.tar.gz \
  https://github.com/actions/runner/releases/download/v2.336.0/actions-runner-linux-arm64-2.336.0.tar.gz
tar xzf runner.tar.gz && rm runner.tar.gz

# .NET runtime libs the runner needs
sudo ./bin/installdependencies.sh

# token from: repo Settings -> Actions -> Runners -> New self-hosted runner
# (valid one hour, single use)
./config.sh \
  --url https://github.com/warped-pinball/vector \
  --token <REGISTRATION_TOKEN> \
  --labels vector-hil \
  --unattended
```

```bash
# --- bench wifi credentials ------------------------------------------------
# the runner reads .env at service start and passes these to every job
cat >> ~/actions-runner/.env <<'EOF'
VECTOR_HIL_WIFI_SSID=your-bench-ssid
VECTOR_HIL_WIFI_PASSWORD=your-bench-password
EOF
chmod 600 ~/actions-runner/.env
```

```bash
# --- run as a service ------------------------------------------------------
cd ~/actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```

The runner should now show **Idle** under Settings → Actions → Runners with the `vector-hil`
label. Workflows target it with `runs-on: [self-hosted, vector-hil]`.

`.env` is only read when the service starts, so `sudo ./svc.sh stop && sudo ./svc.sh start`
after changing the credentials.

## Smoke test

Put this on a branch and dispatch it to confirm the full path works:

```yaml
name: HIL smoke
on: workflow_dispatch

jobs:
  smoke:
    runs-on: [self-hosted, vector-hil]
    timeout-minutes: 10
    steps:
      - run: ~/vector/.venv/bin/python ~/vector/dev/detect_boards.py
      - run: test -n "$VECTOR_HIL_WIFI_SSID" && echo "wifi env present"
```

## If something breaks

Add these back only as needed:

- **Jobs get OOM-killed** (`dmesg -T | grep -i oom`) — 512 MB is tight on a Zero 2 W.
  `sudo apt install -y zram-tools` gets you compressed swap with no further config.
- **Runner won't start, globalization error** — `installdependencies.sh` didn't get libicu.
  Re-run it, or add `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` to `~/actions-runner/.env`.
- **`Permission denied` on `/dev/ttyACM*`** — the login user isn't in `dialout`.
  `sudo usermod -aG dialout $USER`, then reboot.
- **You need to pin a specific physical board** rather than a board type — `detect_boards.py`
  identifies boards by querying `systemConfig.vectorSystem`, so port order doesn't matter.
  Only add udev rules if you need to tell two boards of the same type apart.

See [DESIGN.md](DESIGN.md) for the test architecture and the security model for fork PRs.
