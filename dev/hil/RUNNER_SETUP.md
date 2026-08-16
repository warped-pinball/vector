# HIL Bench — Pi Runner Setup

Sets up a Raspberry Pi with Vector boards attached as a GitHub Actions runner, deployed as a
[Raspberry Pi Connect script artefact](https://www.raspberrypi.com/documentation/services/connect.html#remoteupdate-intro).

Assumes the Pi is assembled, boards are on a powered USB hub, arm64 userland, and the boards
sit on the same VLAN as the Pi. Board detection and flashing use the repo's existing dev
pipeline (`dev/detect_boards.py`, `dev/sync.py`), so there is nothing bench-specific to
configure.

Files live in [`ota/`](ota/):

| File | Purpose |
|---|---|
| `hil-runner-setup.sh` | the script artefact — runs as root on the Pi |
| `hil-runner-setup.yaml` | the otamaker manifest |

## Deploy

**1. Get a registration token.** Repo → Settings → Actions → Runners → New self-hosted
runner. It is single-use and **valid for one hour**, so do this immediately before packaging.

**2. Fill in the config block** at the top of `ota/hil-runner-setup.sh`:

```sh
RUNNER_USER="pi"
REGISTRATION_TOKEN="PASTE_REGISTRATION_TOKEN"
WIFI_SSID="PASTE_BENCH_SSID"
WIFI_PASSWORD="PASTE_BENCH_PASSWORD"
```

The script refuses to run if the placeholders are still in place, so a half-filled artefact
fails immediately and visibly rather than registering a runner with a broken environment.

**3. Build the artefact:**

```bash
cd dev/hil/ota
otamaker hil-runner-setup.yaml
```

This produces a `.tar.zst` and prints its SHA-256.

**4. Deploy** through Raspberry Pi Connect to the bench Pi.

**5. Watch it run** — the script logs each phase to the device journal:

```bash
journalctl -t rpi-ota-connector -f
```

Expect roughly five minutes, most of it `pip install` building the dev pipeline.

> **Do not commit a filled-in script.** The token is single-use and short-lived, but the WiFi
> password is not. Fill in a working copy, package it, and discard it.

## What the script does

Runs as root, per the Connect artefact contract, and drops to `$RUNNER_USER` via `runuser`
for everything that shouldn't be root — the Actions runner refuses to be configured as root,
and shouldn't run as root regardless.

1. Installs `git`, `python3-venv`, `curl`; adds the runner user to `dialout` for serial access
2. Clones (or fetches) the repo and builds a venv from `dev/requirements.txt`
3. Runs `dev/detect_boards.py` and logs what it found
4. Downloads the Actions runner, registers it with the `vector-hil` label
5. Writes bench credentials to the runner's `.env`
6. Installs and starts the systemd service, then verifies the unit is actually active

Exit codes follow the Connect contract: `0` success, `1` failure, `2` success-plus-reboot.
The script never returns `2` — nothing it does needs a reboot, because systemd reads the new
`dialout` membership when it starts the service.

**Board detection is non-fatal.** A board that is unplugged or mid-reset logs a warning and
the deployment continues, rather than failing the whole setup over a transient USB state.
Bench health is the pre-job check's job, not the installer's.

**It is safe to re-run.** Existing clone gets fetched instead of re-cloned, existing runner
download and registration are left alone, and `.env` is rewritten in place — only the
`VECTOR_HIL_*` lines it owns, so anything else you set there survives. Re-running it is the
normal way to refresh WiFi credentials or pull a newer harness.

To re-register against a different repo or token, remove the registration first — the script
deliberately won't do this behind your back:

```bash
cd ~/actions-runner && sudo ./svc.sh uninstall && ./config.sh remove --token <REMOVAL_TOKEN>
```

## Verify

The runner should show **Idle** under Settings → Actions → Runners with the `vector-hil`
label. Confirm end to end with a workflow on a branch:

```yaml
name: HIL smoke
on: workflow_dispatch

jobs:
  smoke:
    runs-on: [self-hosted, vector-hil]
    timeout-minutes: 10
    steps:
      - run: $VECTOR_HIL_VENV/bin/python $VECTOR_HIL_REPO/dev/detect_boards.py
      - run: test -n "$VECTOR_HIL_WIFI_SSID" && echo "wifi env present"
```

`VECTOR_HIL_VENV` and `VECTOR_HIL_REPO` are exported into every job from `.env`, so workflows
don't hardcode paths.

## If something breaks

- **Where did it fail?** `journalctl -t rpi-ota-connector` — every phase is logged, and each
  failure exits with a specific message.
- **`runner registration failed`** — almost always an expired token. They last one hour.
  Get a fresh one, refill, rebuild, redeploy.
- **Jobs get OOM-killed** (`dmesg -T | grep -i oom`) — 512 MB is tight on a Zero 2 W.
  `sudo apt install -y zram-tools` gets you compressed swap with no further config.
- **Runner won't start, globalization error** — libicu missing. Re-run
  `~/actions-runner/bin/installdependencies.sh`, or add
  `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` to `~/actions-runner/.env`.
- **`.env` changes have no effect** — it is read at service start.
  `cd ~/actions-runner && sudo ./svc.sh stop && sudo ./svc.sh start`.
- **You need to tell two boards of the same type apart** — `detect_boards.py` identifies
  boards by querying `systemConfig.vectorSystem`, so port order doesn't matter for distinct
  board types. Only add udev rules if you have two of the same type.

See [DESIGN.md](DESIGN.md) for the test architecture and the security model for fork PRs.
