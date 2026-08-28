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

**The clone is pinned, not floating.** After fetching, the script checks out `origin/$REPO_BRANCH`
(default `main`) as a detached HEAD, so the bench always runs a known ref rather than whatever
was last left checked out. It refuses to run if the clone has uncommitted changes rather than
discarding them — if you've been debugging by hand there, commit, stash, or delete the clone.

Overridable via environment if you need them: `REPO_URL`, `REPO_BRANCH`, `RUNNER_LABELS`,
`RUNNER_VERSION`, `RUNNER_ARCH`.

### On WiFi credentials with unusual characters

The runner reads `.env` line by line, splits on the first `=`, and takes the rest of the line
verbatim ([`Runner.Listener/Program.cs`](https://github.com/actions/runner/blob/v2.336.0/src/Runner.Listener/Program.cs#L179-L197)) —
there is no `EnvironmentFile=` in the generated systemd unit and `runsvc.sh` doesn't source it
either. So spaces, quotes and backslashes in an SSID or password are safe and must **not** be
escaped; quoting would store literal quote characters. A newline is the one value that cannot
be represented, and the script rejects it up front.

### Why not an ephemeral runner

DESIGN.md §9 calls for `--ephemeral`. This script registers a persistent runner instead, which
is a deliberate deviation with a reason: ephemeral runners deregister after every job, so
something has to mint a fresh registration token each time — which means storing a PAT with
`administration: write` on the Pi, readable by the same user that runs job code. That PAT is a
much more valuable secret than the runner's own credentials, which only let you receive jobs.

The trade works because of the trust model: under `workflow_run`, the Pi only ever executes
harness code from a trusted ref (DESIGN.md §4), so the "poison the workspace for the next job"
attack that ephemeral runners defend against has no foothold. Revisit this if the Pi ever
starts executing PR-authored code — at that point ephemeral runners via JIT config stop being
optional.

To re-register against a different repo or token, remove the registration first — the script
deliberately won't do this behind your back:

```bash
cd ~/actions-runner && sudo ./svc.sh uninstall && ./config.sh remove --token <REMOVAL_TOKEN>
```

## Telling the boards apart

Nothing on a board reports what hardware it is. `systemConfig.vectorSystem` is a build-time
constant baked into whatever was last flashed, so `dev/detect_boards.py` tells you what a board
is *running*, not what it is — which is exactly wrong after a mis-flash. `machine.unique_id()`
is the RP2040 chip id: stable per board and survives reflashing, but silent about the system.

Since the bench boards are dedicated, pin them by chip id once and the question goes away.

Blink each board in turn and watch the bench:

```bash
cd ~/vector && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python dev/hil/flash_and_check.py --identify
```

(`$VECTOR_HIL_VENV` is exported by the runner *service*, so it is not set in a login shell —
hence the explicit `.venv` path here.)

Then record what you saw:

```bash
echo 'VECTOR_HIL_BOARD_MAP=<chip1>=sys11,<chip2>=wpc,<chip3>=data_east' >> ~/actions-runner/.env
cd ~/actions-runner && sudo ./svc.sh stop && sudo ./svc.sh start
```

With the map set, `flash_and_check.py` uses it and ignores self-report entirely. Without it,
the harness falls back to self-report but **refuses to flash when two boards claim the same
system**, since that means at least one is running firmware for a system it isn't wired for.

`--inventory-only` prints the chip ids without blinking or flashing anything.

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

## Running the harnesses by hand

Both take the bench venv on `PATH` — the runner's `.env` provides it inside a job, but a
login shell does not read it:

```bash
cd ~/vector && export PATH="$PWD/.venv/bin:$PATH"

# flash every board and health-check its API (G1/G2)
.venv/bin/python dev/hil/flash_and_check.py

# boot every board against every config it can be flashed with (G3)
.venv/bin/python dev/hil/config_matrix.py

# ...or just the WPC board, first five configs, no reflash
.venv/bin/python dev/hil/config_matrix.py --target wpc --limit 5 --skip-flash
```

A full config matrix is roughly 20–22s per config per board (measured on the bench) and WPC
alone has 63, so budget well over half an hour for an unfiltered run. `--configs`, `--limit` and `--target` are there
to keep an iteration loop short; `--changed-since REF` runs the configs a branch touched
first, which is what the workflow does on a push.

The matrix leaves each board on its generic config when it finishes, including after a
failure, so a run never strands a board on a game config you did not ask for. If a board
stops answering it is abandoned after two consecutive setup failures and the run moves on to
the next board, rather than timing out against a board that is not coming back.

**Never `cat /dev/ttyACM*` to watch a board.** A tty reverts to ECHO-on once every handle is
closed, so a bare `cat` makes the kernel echo the board's own output back into it, and the
board then tries to parse its log lines as USB API requests. Use `stty -F /dev/ttyACM0 raw
-echo 115200` first, or `mpremote connect /dev/ttyACM0 repl`.

## Recovering a wedged board

A board can deadlock with its USB device still enumerated and the firmware gone: the port is
there, `mpremote` opens it, nothing answers. `dev/hil/recover.py` escalates through four
rungs and stops as soon as the board replies. Run it from
[`hil-recover.yml`](../../.github/workflows/hil-recover.yml), or by hand:

```bash
cd ~/vector && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python dev/hil/recover.py
```

It opens with a report of which rungs this runner can actually use. As measured on the bench
on 2026-08-28:

| rung | state | what it needs |
|---|---|---|
| drain the console | works | serial access, which the `dialout` group already gives |
| reset the USB device | **unavailable** | write access to `/dev/bus/usb/*` — a udev rule |
| power cycle the hub port | **unavailable** | `sudo apt install uhubctl`, and a hub that switches port power |
| reflash via TrenchCoat | works | `udisksctl`, which is present |

The two unavailable rungs are worth enabling — they are the non-destructive ones, and without
them a wedged board goes straight from "send it a Ctrl-C" to "wipe its flash". For the USB
reset, a rule like this grants the runner user write access to the boards' USB nodes:

```
# /etc/udev/rules.d/60-vector-hil.rules
SUBSYSTEM=="usb", ATTR{idVendor}=="2e8a", MODE="0660", GROUP="dialout"
```

then `sudo udevadm control --reload && sudo udevadm trigger`. Note the boards are USB bus
powered, so a hub with per-port power switching makes the power rung a genuine cold boot —
the most reliable recovery short of a reflash.

The reflash rung hands the board to [TrenchCoat](https://github.com/warped-pinball/trench-coat),
pinned by commit in `dev/hil/trench_coat.py`, which resets into the ROM bootloader, wipes the
flash with `nuke.uf2` and writes the real firmware. It is destructive: run
`dev/hil/flash_and_check.py` afterwards to put Vector back on the board.

See [DESIGN.md](DESIGN.md) for the test architecture and the security model for fork PRs.
