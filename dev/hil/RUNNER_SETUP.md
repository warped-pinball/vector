# HIL Bench — Raspberry Pi Runner Setup

How to turn a Raspberry Pi Zero 2 W with Vector boards attached into a GitHub Actions
self-hosted runner that can execute the hardware tests described in [DESIGN.md](DESIGN.md).

**Assumes:** the Pi is assembled, the boards are wired to a powered USB hub, Raspberry Pi OS
is installed, and you can reach the Pi over Raspberry Pi Connect. Everything below is done
from a shell on the Pi.

**Produces:** a runner labelled `vector-hil` attached to `warped-pinball/vector`, a pinned
Python environment, stable device names for each board, and a health check that fails a job
early instead of confusingly.

Work through the phases in order. Each ends with a verification step — don't move on until
it passes.

---

## Phase 0 — Confirm the starting point

```bash
cat /etc/os-release | grep PRETTY_NAME
uname -m                      # kernel architecture
dpkg --print-architecture     # userland architecture  <- this is the one that matters
free -h
python3 -V
```

Two things to note before continuing.

**Use `dpkg --print-architecture`, not `uname -m`, to pick the runner build.** Raspberry Pi OS
routinely runs a 64-bit kernel with a 32-bit userland, so `uname -m` reports `aarch64` while
the userland is `armhf` and only the 32-bit runner will work. `dpkg --print-architecture`
reports the userland, which is what the runner binary has to match.

| `dpkg --print-architecture` | Runner build |
|---|---|
| `armhf` | `linux-arm` |
| `arm64` | `linux-arm64` |

**Raspberry Pi OS Lite is strongly preferred on 512 MB.** If this is a desktop image, the
runner will be fighting the compositor for RAM. Also note Bookworm ships Python 3.11 with
PEP 668 enabled, so `pip install` outside a virtualenv is refused — Phase 3 uses a venv.

---

## Phase 1 — Memory headroom

512 MB is the real constraint on this box. The runner is a .NET process (~150–250 MB
resident), plus Python, plus three concurrent `mpremote` sessions. Without help it will
OOM-kill mid-job, and an OOM kill in the middle of a config sweep looks exactly like a
firmware hang — you'll waste an afternoon on it.

Add compressed RAM swap first, since it costs no SD card writes:

```bash
sudo apt update
sudo apt install -y zram-tools
sudo sed -i 's/^#\?ALGO=.*/ALGO=zstd/;s/^#\?PERCENT=.*/PERCENT=60/' /etc/default/zramswap
sudo systemctl restart zramswap
```

Then raise the on-disk swapfile as an overflow tier:

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo sed -i 's/^#\?CONF_MAXSWAP=.*/CONF_MAXSWAP=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

Prefer zram over the SD card, and don't let the kernel swap eagerly:

```bash
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-hil.conf
sudo sysctl --system
```

**Verify:**

```bash
swapon --show      # expect /dev/zram0 (higher priority) and /var/swap
free -h
```

You want zram listed with a higher priority number than the file swap. If you later see jobs
slow to a crawl, check `vmstat 1` for sustained `si`/`so` — that's disk swap thrashing, and
the fix is fewer parallel boards, not a bigger swapfile.

---

## Phase 2 — User, packages, layout

Run the runner as a dedicated unprivileged user. It needs `dialout` for serial access to the
boards.

```bash
sudo adduser --disabled-password --gecos "" hilrunner
sudo usermod -aG dialout hilrunner
```

Deliberately **no sudo rights** for `hilrunner`, and no docker group.

```bash
sudo apt install -y git curl jq python3-venv python3-full usbutils
```

Directory layout — runner and harness support files kept separate:

```bash
sudo mkdir -p /opt/vector-hil/{hooks,logs}
sudo mkdir -p /etc/vector-hil
sudo mkdir -p /opt/actions-runner
sudo chown -R hilrunner:hilrunner /opt/vector-hil /opt/actions-runner
sudo chown root:hilrunner /etc/vector-hil
sudo chmod 750 /etc/vector-hil
```

---

## Phase 3 — Python environment

The workflow runs from a trusted ref and shouldn't be building a venv on every job — that's
minutes of wall clock on this hardware. Create it once, pinned:

```bash
sudo -u hilrunner python3 -m venv /opt/vector-hil/venv
sudo -u hilrunner /opt/vector-hil/venv/bin/pip install --upgrade pip
sudo -u hilrunner /opt/vector-hil/venv/bin/pip install \
  mpremote==1.23.0 \
  pytest==9.1.1 \
  pytest-timeout==2.5.0 \
  pytest-xdist==3.8.0 \
  PyYAML==6.0.3 \
  requests==2.34.2
```

`mpremote` is pinned to 1.23.0 to match `dev/requirements.txt`. `pytest-xdist` is what lets
the suite fan out across boards — the design's parallelism assumes it.

`mpy-cross` is deliberately **not** installed here. Builds happen on GitHub-hosted runners;
the Pi only consumes artifacts. If you find yourself wanting to build on the Pi, stop and
re-read the threat model in DESIGN.md §3 — that's the boundary this whole design rests on.

**Verify:**

```bash
sudo -u hilrunner /opt/vector-hil/venv/bin/python -c "import pytest, yaml, requests; print('ok')"
sudo -u hilrunner /opt/vector-hil/venv/bin/mpremote --help >/dev/null && echo "mpremote ok"
```

---

## Phase 4 — Stable board device names

`/dev/ttyACM0` ordering is not stable across reboots or re-enumeration. If the harness
addresses boards that way, a reboot silently swaps which board runs which test suite and you
get results attributed to the wrong hardware. Pin each board to a symlink by its USB serial.

With all boards plugged in, list them:

```bash
/opt/vector-hil/venv/bin/mpremote devs
```

For each port, get the identifying attributes:

```bash
for d in /dev/ttyACM*; do
  echo "=== $d"
  udevadm info -a -n "$d" 2>/dev/null | grep -m3 -E 'ATTRS\{(idVendor|idProduct|serial)\}'
done
```

Raspberry Pi's vendor ID is `2e8a`; a Pico running MicroPython typically enumerates as
product `0005`. **Use whatever the command above actually prints** rather than trusting those
values — the firmware build determines them.

Identify which physical board is which by asking each one:

```bash
for d in /dev/ttyACM*; do
  echo -n "$d -> "
  /opt/vector-hil/venv/bin/mpremote connect "$d" exec \
    "import systemConfig; print(systemConfig.vectorSystem, systemConfig.SystemVersion)" 2>/dev/null \
    || echo "(no response)"
done
```

That's the same probe `dev/detect_boards.py` uses. Now write the rules, substituting the real
serial numbers:

```bash
sudo tee /etc/udev/rules.d/99-vector-hil.rules >/dev/null <<'EOF'
# Vector HIL bench — stable names by USB serial.
# Get serials with: udevadm info -a -n /dev/ttyACM0 | grep ATTRS{serial}
SUBSYSTEM=="tty", ATTRS{idVendor}=="2e8a", ATTRS{serial}=="REPLACE_SYS11_SERIAL",     SYMLINK+="vector-sys11-a",     GROUP="dialout", MODE="0660"
SUBSYSTEM=="tty", ATTRS{idVendor}=="2e8a", ATTRS{serial}=="REPLACE_WPC_SERIAL",       SYMLINK+="vector-wpc-a",       GROUP="dialout", MODE="0660"
SUBSYSTEM=="tty", ATTRS{idVendor}=="2e8a", ATTRS{serial}=="REPLACE_DATA_EAST_SERIAL", SYMLINK+="vector-data-east-a", GROUP="dialout", MODE="0660"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
```

**Verify:**

```bash
ls -l /dev/vector-*
```

You should see three symlinks. Unplug and replug the hub, confirm they come back pointing at
the right boards, and confirm `hilrunner` can open them:

```bash
sudo -u hilrunner /opt/vector-hil/venv/bin/mpremote connect /dev/vector-wpc-a \
  exec "import systemConfig; print(systemConfig.vectorSystem)"
```

If that fails with a permissions error, `hilrunner`'s `dialout` membership hasn't taken
effect — log out and back in, or reboot.

---

## Phase 5 — Network

DESIGN.md §5 puts the boards on a VLAN isolated from the LAN. The Zero 2 W has a single
radio and no ethernet, which constrains how that gets built: **the Pi cannot be on the LAN
and the bench VLAN at the same time.**

The workable arrangement with one radio:

- The bench VLAN has its own SSID. The Pi joins **only** that SSID.
- On the router: allow the Pi's MAC out to the internet (it needs github.com); deny the board
  MACs any WAN access; deny the whole VLAN any access to the LAN.
- Boards reach the Pi's update server directly — same subnet, no routing needed.
- Give each board a static DHCP lease so the manifest IPs stay put.

If your router can't do per-MAC egress rules on a VLAN, the fallback is a USB ethernet
adapter on the hub for the LAN uplink, leaving `wlan0` for the bench. Note that this is
router configuration, not Pi configuration — the Pi side is just joining the right SSID.

**Verify from the Pi:**

```bash
curl -sS -o /dev/null -w "github: %{http_code}\n" https://api.github.com
ping -c2 10.42.7.11   # a board's static lease
```

**Verify isolation actually holds** — this is the part people skip and regret. From a board's
REPL, confirm it cannot reach the LAN:

```bash
/opt/vector-hil/venv/bin/mpremote connect /dev/vector-wpc-a exec "
import socket
try:
    s = socket.socket(); s.settimeout(3)
    s.connect(socket.getaddrinfo('192.168.1.1', 80)[0][-1])   # your LAN gateway
    print('REACHABLE - isolation is NOT working')
except Exception as e:
    print('blocked (good):', e)
"
```

If that prints `REACHABLE`, stop and fix the router before attaching the runner. The entire
security argument for running untrusted firmware on this bench depends on that path being
closed.

### Optional: DNS override for `/api/update/check`

`/api/update/check` fetches `software.warpedpinball.com`. Rather than opening egress for it,
serve a canned response locally so the test is deterministic (DESIGN.md §5):

```bash
sudo apt install -y dnsmasq
echo "address=/software.warpedpinball.com/10.42.7.1" | \
  sudo tee /etc/dnsmasq.d/vector-hil.conf
sudo systemctl restart dnsmasq
```

Only do this if the Pi is the VLAN's DNS server. If the router handles DHCP/DNS there, put
the override on the router instead — running a second DHCP server on the segment will cause
problems that are annoying to diagnose.

---

## Phase 6 — Bench manifest and secrets

The manifest describes the bench; it lives on the Pi, not in git (DESIGN.md §6).

```bash
sudo tee /etc/vector-hil/bench.yaml >/dev/null <<'EOF'
boards:
  - id: sys11-a
    target: sys11
    hardware: sys11
    serial: /dev/vector-sys11-a
    ip: 10.42.7.11
  - id: wpc-a
    target: wpc
    hardware: wpc
    serial: /dev/vector-wpc-a
    ip: 10.42.7.12
  - id: data-east-a
    target: data_east
    hardware: data_east
    serial: /dev/vector-data-east-a
    ip: 10.42.7.13

network:
  update_server: http://10.42.7.1:8080

secrets_file: /etc/vector-hil/secrets.yaml
EOF

sudo tee /etc/vector-hil/secrets.yaml >/dev/null <<'EOF'
wifi_ssid: "BENCH-SSID"
wifi_password: "..."
game_password: "..."
EOF

sudo chown root:hilrunner /etc/vector-hil/bench.yaml /etc/vector-hil/secrets.yaml
sudo chmod 640 /etc/vector-hil/bench.yaml /etc/vector-hil/secrets.yaml
```

These are bench credentials for an isolated segment, not production secrets — but keep them
off GitHub regardless. Group-readable by `hilrunner` and nothing wider.

Adding a board later is a udev rule plus an entry here. No test changes.

---

## Phase 7 — Install the Actions runner

Pick the build from Phase 0's `dpkg --print-architecture`.

```bash
cd /opt/actions-runner
RUNNER_VERSION=2.336.0

# armhf userland:
RUNNER_ARCH=arm    RUNNER_SHA=44a300f322a1b5bccfe0b146cf3ca74f27000eb8afed761d1ffd90be035969d4
# arm64 userland — use these two lines instead:
# RUNNER_ARCH=arm64  RUNNER_SHA=58b758e420b87093fbd4bfddd368074960053e2f1388f01848c82624b90f27d1

sudo -u hilrunner curl -fSL -o runner.tar.gz \
  "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"

echo "${RUNNER_SHA}  runner.tar.gz" | sha256sum -c - || { echo "CHECKSUM MISMATCH"; rm -f runner.tar.gz; }
sudo -u hilrunner tar xzf runner.tar.gz && sudo -u hilrunner rm runner.tar.gz
```

Those checksums were computed from the published v2.336.0 artifacts. Verify before extracting
— on a box that will be handling artifacts from public PRs, "I'll check it later" is how you
end up not checking it.

The runner is a .NET application and needs a few system libraries:

```bash
sudo ./bin/installdependencies.sh
```

Get a registration token from
**Settings → Actions → Runners → New self-hosted runner** on `warped-pinball/vector`. It is
valid for one hour and is single-use.

```bash
sudo -u hilrunner ./config.sh \
  --url https://github.com/warped-pinball/vector \
  --token <REGISTRATION_TOKEN> \
  --name vector-hil-pi \
  --labels vector-hil \
  --work _work \
  --unattended --replace
```

The `vector-hil` label is what `hil.yml` will target via
`runs-on: [self-hosted, vector-hil]`. Don't rely on the bare `self-hosted` label — the moment
there's a second runner anywhere in the org, jobs start landing on the wrong machine.

### A note on ephemeral runners

DESIGN.md §9 calls for `--ephemeral`. Deliberately not doing that in this first setup, for a
specific reason: an ephemeral runner deregisters after every job, so something has to mint a
fresh registration token for each one. That means storing a PAT with `administration: write`
on the Pi — readable by the same user that runs job code. That PAT is a considerably more
valuable secret than the runner's own credentials, which only let you receive jobs.

The trade is acceptable here because of the trust model: under `workflow_run`, the Pi only
ever executes harness code from the default branch (DESIGN.md §4). It never runs PR-authored
host code, so the "poison the workspace for the next job" attack that ephemeral runners
defend against doesn't have a foothold. The job hooks in Phase 8 cover the rest.

Revisit this if the Pi ever starts executing PR-authored code — at that point ephemeral
runners via JIT config stop being optional.

---

## Phase 8 — Job hooks

Two hooks: a pre-job health check that fails fast when the bench isn't sane, and a post-job
cleanup.

```bash
sudo -u hilrunner tee /opt/vector-hil/hooks/pre-job.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
# Fail the job immediately if the bench isn't healthy, rather than letting the
# tests fail in a way that looks like a firmware regression.
set -euo pipefail

VENV=/opt/vector-hil/venv/bin
MANIFEST=${VECTOR_HIL_BENCH:-/etc/vector-hil/bench.yaml}

echo "::group::Bench health check"
rc=0
for dev in $("$VENV/python" -c "
import yaml
for b in yaml.safe_load(open('$MANIFEST'))['boards']:
    print(b['serial'])
"); do
  if [[ ! -e "$dev" ]]; then
    echo "::error::$dev is missing - board not enumerated"
    rc=1
    continue
  fi
  if out=$(timeout 20 "$VENV/mpremote" connect "$dev" exec \
        "import systemConfig; print(systemConfig.vectorSystem)" 2>&1); then
    echo "  $dev -> ${out//[$'\r\n']/}"
  else
    echo "::error::$dev did not respond to mpremote: $out"
    rc=1
  fi
done

avail=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
echo "  available memory: ${avail} MB"
if [[ $avail -lt 80 ]]; then
  echo "::warning::low memory before job start (${avail} MB)"
fi

echo "::endgroup::"
exit $rc
EOF

sudo -u hilrunner tee /opt/vector-hil/hooks/post-job.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
# Best-effort cleanup. Never fail the job from here - the tests already ran.
set -uo pipefail

VENV=/opt/vector-hil/venv/bin
MANIFEST=${VECTOR_HIL_BENCH:-/etc/vector-hil/bench.yaml}

for dev in $("$VENV/python" -c "
import yaml
for b in yaml.safe_load(open('$MANIFEST'))['boards']:
    print(b['serial'])
" 2>/dev/null); do
  [[ -e "$dev" ]] || continue
  timeout 15 "$VENV/mpremote" connect "$dev" exec \
    "import machine; machine.reset()" >/dev/null 2>&1 || true
done

find /opt/actions-runner/_work -mindepth 1 -maxdepth 1 \
  ! -name '_tool' ! -name '_temp' -exec rm -rf {} + 2>/dev/null || true

exit 0
EOF

sudo -u hilrunner chmod +x /opt/vector-hil/hooks/*.sh
```

Register them in the runner's `.env`, which the service reads at start:

```bash
sudo -u hilrunner tee -a /opt/actions-runner/.env >/dev/null <<'EOF'
ACTIONS_RUNNER_HOOK_JOB_STARTED=/opt/vector-hil/hooks/pre-job.sh
ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/opt/vector-hil/hooks/post-job.sh
VECTOR_HIL_BENCH=/etc/vector-hil/bench.yaml
VECTOR_HIL_VENV=/opt/vector-hil/venv
EOF
```

`.env` is only read when the service starts, so restart it after any change here.

**Verify:**

```bash
sudo -u hilrunner /opt/vector-hil/hooks/pre-job.sh && echo "PRE-JOB OK"
```

---

## Phase 9 — Run as a service

```bash
cd /opt/actions-runner
sudo ./svc.sh install hilrunner
sudo ./svc.sh start
sudo ./svc.sh status
```

**Verify** the runner shows **Idle** under Settings → Actions → Runners, with the `vector-hil`
label attached.

```bash
journalctl -u "actions.runner.warped-pinball-vector.vector-hil-pi.service" -f
```

The runner auto-updates itself by default. Leave that on — GitHub stops dispatching jobs to
runners that fall too far behind. Just be aware an update pulls ~77 MB, so an occasional job
will start slowly.

---

## Phase 10 — End-to-end check

Before there's any harness code, confirm the whole path works with a throwaway workflow on a
branch:

```yaml
name: HIL smoke
on: workflow_dispatch

jobs:
  smoke:
    runs-on: [self-hosted, vector-hil]
    timeout-minutes: 10
    steps:
      - name: Report bench state
        run: |
          source "$VECTOR_HIL_VENV/bin/activate"
          python - <<'PY'
          import os, subprocess, yaml
          bench = yaml.safe_load(open(os.environ["VECTOR_HIL_BENCH"]))
          for b in bench["boards"]:
              out = subprocess.run(
                  ["mpremote", "connect", b["serial"], "exec",
                   "import systemConfig; print(systemConfig.vectorSystem, systemConfig.SystemVersion)"],
                  capture_output=True, text=True, timeout=30)
              print(f'{b["id"]:14} {out.stdout.strip() or out.stderr.strip()}')
          PY
```

Dispatch it. A green run that prints all three boards and their versions means the runner,
the venv, the udev names, the manifest, and the hooks are all wired correctly — which is
everything Phase 0–9 was for.

---

## Maintenance and troubleshooting

**SD card wear.** This bench writes a lot: artifact downloads, `_work` churn, swap. Use a
decent A2 card, keep the file swap modest, and treat the card as consumable. Take an image
once the setup is verified so a rebuild is a restore rather than a repeat of this document.

**Log growth.** Runner diagnostic logs accumulate in `_diag`:

```bash
sudo tee /etc/logrotate.d/vector-hil >/dev/null <<'EOF'
/opt/actions-runner/_diag/*.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
EOF
```

**A board stops responding.** Expected occasionally — recovery is software-only by decision
(DESIGN.md §10), so `machine.reset()` over `mpremote` is the first move. If MicroPython
itself won't come up, the board needs a physical BOOTSEL press and a reflash with
`trench-coat/uf2/nuke.uf2`. The pre-job hook will keep failing jobs loudly until that's done,
which is the intended behaviour — a silently absent board would attribute its tests to
nothing.

**Jobs get OOM-killed.** Check `dmesg -T | grep -i oom`. Reduce `pytest-xdist` parallelism
before touching swap; three concurrent `mpremote` sessions plus the runner is close to the
ceiling on 512 MB.

**Runner shows Offline after a reboot.** `sudo ./svc.sh status`; the service is enabled at
install but confirm with `systemctl is-enabled`.

**Permission denied on `/dev/vector-*`.** `hilrunner` isn't in `dialout` yet, or the group
change hasn't been picked up by the running service. Restart the service.

**Symlinks point at the wrong board after a hub replug.** A serial number in the udev rules
is wrong or duplicated. Re-run the Phase 4 identification loop.

---

## What this does not cover

- The `hil.yml` workflow and the `dev/hil` harness — not written yet; see DESIGN.md §4 and §7.
- The `hardware-lab` GitHub Environment and fork gating — repo settings, not Pi settings
  (DESIGN.md §4).
- The update file server the OTA tests need on `10.42.7.1:8080` — the harness starts that
  itself per-run (DESIGN.md §7, `update_server.py`).
- Router and VLAN configuration, which is where the isolation guarantee actually lives.
