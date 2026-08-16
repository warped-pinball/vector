# HIL Bench — Pi Runner Setup

Minimal setup to make a Raspberry Pi with Vector boards attached run GitHub Actions jobs.
Assumes the Pi is assembled, boards are on a powered USB hub, and you have a shell on it.

Board detection and flashing use the repo's existing dev pipeline (`dev/detect_boards.py`,
`dev/sync.py`), so there is nothing bench-specific to configure.

```bash
# --- system packages -------------------------------------------------------
sudo apt update
sudo apt install -y git python3-venv curl

# serial access to the Picos; log out and back in for this to take effect
sudo usermod -aG dialout $USER
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

# pick the build matching the *userland* arch (not `uname -m`, which can differ)
ARCH=$([ "$(dpkg --print-architecture)" = arm64 ] && echo arm64 || echo arm)
curl -fSLo runner.tar.gz \
  "https://github.com/actions/runner/releases/download/v2.336.0/actions-runner-linux-${ARCH}-2.336.0.tar.gz"

# optional: verify the download
sha256sum runner.tar.gz
#   arm   -> 44a300f322a1b5bccfe0b146cf3ca74f27000eb8afed761d1ffd90be035969d4
#   arm64 -> 58b758e420b87093fbd4bfddd368074960053e2f1388f01848c82624b90f27d1

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

# run as a service so it survives reboots
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```

The runner should now show **Idle** under Settings → Actions → Runners with the `vector-hil`
label. Workflows target it with `runs-on: [self-hosted, vector-hil]`.

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
```

## If something breaks

Add these back only as needed:

- **Jobs get OOM-killed** (`dmesg -T | grep -i oom`) — 512 MB is tight on a Zero 2 W.
  `sudo apt install -y zram-tools` gets you compressed swap with no further config.
- **`Permission denied` on `/dev/ttyACM*`** — the `dialout` group hasn't taken effect.
  Reboot, then `sudo ./svc.sh stop && sudo ./svc.sh start`.
- **Board ordering shifts between runs and you start caring which is which** — `detect_boards.py`
  identifies boards by querying `systemConfig.vectorSystem`, so it doesn't care about port
  order. Only add udev rules if you need to pin a *specific physical board* rather than a
  board type.
- **Runner won't start, globalization error** — `installdependencies.sh` didn't get libicu.
  Re-run it, or set `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` in `~/actions-runner/.env`.

See [DESIGN.md](DESIGN.md) for the test architecture, the security model for fork PRs, and
the network isolation the bench needs before untrusted firmware runs on it.
