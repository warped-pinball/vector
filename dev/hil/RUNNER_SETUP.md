# HIL Bench — Pi Runner Setup

Sets up a Raspberry Pi with Vector boards attached as a GitHub Actions runner.

Assumes the Pi is assembled, boards are on a powered USB hub, arm64 userland, and the boards
sit on the same VLAN as the Pi. Board detection and flashing use the repo's existing dev
pipeline (`dev/detect_boards.py`, `dev/sync.py`), so there is nothing bench-specific to
configure.

> Raspberry Pi Connect's remote update only works on devices with A/B image support — Pi 4 and
> 5 — so the Zero 2 W can't be provisioned that way. This is a plain script you run on the Pi.

## Setup

**1. Get a registration token** from repo → Settings → Actions → Runners → New self-hosted
runner. Single-use, valid one hour.

**2. On the Pi**, as your normal login user (not root):

```bash
curl -fsSLO https://raw.githubusercontent.com/warped-pinball/vector/main/dev/hil/setup-runner.sh
chmod +x setup-runner.sh

export VECTOR_HIL_WIFI_SSID="your-bench-ssid"
export VECTOR_HIL_WIFI_PASSWORD="your-bench-password"
export RUNNER_TOKEN="paste-from-github"

./setup-runner.sh
```

Credentials go in environment variables so they stay out of the script and out of the repo.
Note they will land in your shell history — `unset RUNNER_TOKEN VECTOR_HIL_WIFI_PASSWORD`
afterwards, or prefix the exports with a space if your shell is set to ignore those.

Takes about five minutes, most of it `pip install` building the dev pipeline. It prompts for
sudo once up front rather than midway through.

If you already have the repo cloned at `~/vector`, run `dev/hil/setup-runner.sh` from there
instead of curling it — the script uses `~/vector` either way.

## What it does

1. Installs `git`, `python3-venv`, `curl`; adds you to `dialout` for serial access
2. Clones (or fetches) the repo into `~/vector` and builds a venv from `dev/requirements.txt`
3. Runs `dev/detect_boards.py` and prints what it found
4. Downloads the Actions runner into `~/actions-runner`, registers it with the `vector-hil` label
5. Writes bench credentials to the runner's `.env`
6. Installs and starts the systemd service, then verifies the unit actually stayed up

It runs as your user and calls `sudo` only where needed — the Actions runner refuses to be
configured as root, and shouldn't run as root regardless.

**Board detection is non-fatal.** A board unplugged or mid-reset prints a warning and setup
continues, rather than aborting over a transient USB state.

**Safe to re-run.** An existing clone is fetched rather than re-cloned, an existing runner
download and registration are left alone, and `.env` is rewritten touching only the
`VECTOR_HIL_*` lines it owns. Re-running is the normal way to refresh WiFi credentials or pull
a newer harness — and after the first time you don't need `RUNNER_TOKEN`, since registration is
skipped once the runner exists.

Overridable via environment if you need them: `REPO_URL`, `RUNNER_LABELS`, `RUNNER_VERSION`,
`RUNNER_ARCH`.

To re-register against a different repo or token, remove the registration first — the script
deliberately won't do this behind your back:

```bash
cd ~/actions-runner && sudo ./svc.sh uninstall && ./config.sh remove --token <REMOVAL_TOKEN>
```

## Verify

The runner should show **Idle** under Settings → Actions → Runners with the `vector-hil` label.

End to end, [`.github/workflows/hil-smoke.yml`](../../.github/workflows/hil-smoke.yml) checks
that the runner picks up jobs, the bench environment reaches them, the serial devices are
present and accessible, and every detected board answers over `mpremote`. It fails if no
boards are found or if any detected board doesn't respond.

`VECTOR_HIL_VENV` and `VECTOR_HIL_REPO` are exported into every job from `.env`, so workflows
don't hardcode paths. The smoke job deliberately does no `actions/checkout` — under the design's
trust model the bench runs harness code from the clone it already has, not from a PR.

### Running it before this PR merges

A `workflow_dispatch` workflow isn't dispatchable until it exists on the **default branch**, so
the "Run workflow" button won't appear while this is still a PR. The workflow therefore also
triggers on pushes to this branch — push anything to it and the job runs on the bench:

```bash
git commit --allow-empty -m "trigger hil smoke" && git push
```

Watch it under the repo's Actions tab, or on the Pi itself:

```bash
journalctl -u "$(cat ~/actions-runner/.service)" -f
```

Once this is on `main`, drop the `push:` trigger and use the Run workflow button.

## If something breaks

- **`registration failed`** — almost always an expired token. They last one hour. Get a fresh
  one and re-run.
- **Jobs get OOM-killed** (`dmesg -T | grep -i oom`) — 512 MB is tight on a Zero 2 W.
  `sudo apt install -y zram-tools` gets you compressed swap with no further config.
- **Runner won't start, globalization error** — libicu missing. Re-run
  `~/actions-runner/bin/installdependencies.sh`, or add
  `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` to `~/actions-runner/.env`.
- **`.env` changes have no effect** — it is read at service start.
  `cd ~/actions-runner && sudo ./svc.sh stop && sudo ./svc.sh start`.
- **`Permission denied` on `/dev/ttyACM*`** — the `dialout` group hasn't taken effect in the
  running service. Reboot, or stop and start the service.
- **You need to tell two boards of the same type apart** — `detect_boards.py` identifies boards
  by querying `systemConfig.vectorSystem`, so port order doesn't matter for distinct board
  types. Only add udev rules if you have two of the same type.

See [DESIGN.md](DESIGN.md) for the test architecture and the security model for fork PRs.
