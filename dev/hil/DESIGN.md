# Hardware-in-the-Loop (HIL) Testing — Design

**Status:** design proposal; bench bring-up, the flash/health-check harness (G1/G2) and the config matrix (G3) are implemented and running
**Scope:** a self-hosted GitHub Actions runner driving real Vector boards, safely, from a public repository.

---

## 1. Goals

The first four things we want covered:

| # | Goal | Tier |
|---|---|---|
| G1 | The code boots and the boards run normally | every PR |
| G2 | We can connect to the boards and hit the API | every PR |
| G3 | Every available config can be parsed and boot | every PR |
| G4 | Updating from the last 5 versions to the proposed version works | every PR |

G4 runs on every PR by decision: the update path is critical infrastructure, it is where we most suspect latent problems, and we would rather pay the wall-clock cost than find out at release time. §8 quantifies the cost and §11 lists the levers to dial it back if it becomes painful.

Non-goals for v1: gameplay/bus-level correctness (bare boards, no machine attached), AP-mode setup flow (needs a wire to GPIO22), long-duration soak testing.

## 2. Decisions taken

| Decision | Choice |
|---|---|
| Harness location | All in `warped-pinball/vector`. Bench topology and credentials live on the Pi, not in git. |
| Bench hardware | Bare boards, no machine or bus emulator attached. |
| Board networking | Dedicated VLAN on the existing LAN. |
| Trigger policy | Automatic for branches in `warped-pinball/vector`; forks require a maintainer gate. |
| Board recovery | Software reset only (`machine.reset()` over `mpremote`). |
| Update signing | `skip_signature_check: true` for the upgrade path, plus negative tests that the signature gate still rejects bad packages. |
| Initial inventory | `sys11`, `wpc`, `data_east`. More systems added later. |
| Update matrix cadence | Every PR. Updates are the priority; dial back later only if wall clock becomes a problem. |

---

## 3. Threat model

The repo is public and anyone can open a PR. A PR is, by construction, *untrusted code that we want to run on hardware*. The design has to make that safe rather than avoid it.

### What we are protecting

1. **The LAN.** Anything reachable from the runner or the boards.
2. **`WARPED_PINBALL_PRIVATE_KEY`.** This is the highest-value asset in the org. The matching public key is hardcoded in `src/common/update.py:107`, so a leak means an attacker can sign an update that every Vector in the field will accept. It must never be reachable from a job that runs on the self-hosted runner.
3. **The runner host** and its registration token.
4. **The boards** — recoverable, and the least of the four.

### Attack surfaces, ranked

**(a) Host-side code execution on the Pi.** The big one, and it is broader than it looks. Any of these executes PR-authored code on the runner:

- an obvious `run: python dev/build.py`
- `pip install -r dev/requirements.txt` — a PR can repoint a requirement at a malicious package, or add a `setup.py` that runs at install time
- `pre-commit` hooks — the config names arbitrary repos and revisions
- **`pytest` collection** — `conftest.py` is imported automatically before any test runs. If the harness ever runs from a PR checkout, a PR that only adds a `conftest.py` gets code execution with zero test code executed
- workflow files themselves, if the workflow runs from the PR ref

The mitigation is a single rule, and everything else follows from it:

> **The Pi never checks out or executes PR-authored files. It executes harness code from a trusted ref, and consumes only build *artifacts* from the PR.**

**(b) Board-side code execution.** Intentional — that's the test. `update.py:write_files()` honors `"execute": true` per file and `__import__`s it, so an update package is arbitrary code by design. Contained by assuming every board on the bench is fully compromised at all times, and isolating it accordingly.

**(c) Runner persistence between jobs.** A compromised job leaves something behind for the next one. Mitigated with ephemeral runners and job hooks that wipe state.

**(d) Secret exfiltration.** Mitigated by putting no secrets on the HIL workflow at all.

### A note on the repo question

Putting the harness in a separate repo would **not**, by itself, make any of this safer. A separate repo whose workflow still checked out the PR and ran `pytest` on the Pi is exactly as compromised as an in-repo one. The property that makes this safe is *trusted-ref execution*, not the repo boundary.

So the repo choice is an ergonomics decision, and `vector` is the right home: the harness tests the API, and the API changes in this repo. Keeping them together means an endpoint change and its test ship in one PR and can't drift. The one carve-out is that the *instantiated* bench manifest — serial numbers, IPs, game passwords, WiFi credentials — stays on the Pi. The repo carries the schema and an example, not the instance. That is a "don't publish a map of the lab" measure, not a security boundary.

---

## 4. Execution model

Two stages, split by trust.

### Stage A — build (untrusted, GitHub-hosted)

This already exists: `.github/workflows/build_release.yml` runs on `pull_request`, builds all seven targets, and uploads a `update-files` artifact. Two additions needed:

1. Also upload the full `build/<hardware>` tree per target (tarball). The update packages are only good for OTA; flashing a board from scratch needs the file tree.
2. Write a `pr_meta.json` into the artifact: PR number, head SHA, head repo full name, and the per-target versions. Stage B needs these and cannot reliably get them from the event payload for fork PRs.

No secrets, no self-hosted labels, unchanged trust posture.

### Stage B — hardware (trusted, self-hosted)

A new `.github/workflows/hil.yml`, triggered by **`workflow_run`** on completion of "Build and Deploy".

`workflow_run` is the key primitive. GitHub always runs a `workflow_run` workflow *from the default branch, using the default branch's code*, regardless of what the triggering PR contains. A PR therefore cannot modify `hil.yml`, `dev/hil/**`, `conftest.py`, or the pinned dependency set that the Pi will execute. It gets to supply exactly one thing: the artifact bytes.

```
pull_request (fork or branch)
        │
        ▼
  Build and Deploy  ── GitHub-hosted, untrusted code, no secrets
        │  artifact: update packages + build trees + pr_meta.json
        ▼
  workflow_run: completed
        │
        ├─ gate job (ubuntu-latest): decide auto vs. approval
        │     head repo == warped-pinball/vector → proceed
        │     fork                               → environment `hardware-lab`,
        │                                          required reviewers, job blocks
        ▼
  hil job (runs-on: [self-hosted, vector-hil])
        │  workflow + harness from default branch  ← trusted
        │  artifact downloaded from the build run  ← untrusted payload only
        ▼
  boards on isolated VLAN
        │
        ▼
  check run posted against the PR head SHA
```

**Gating.** Auto for same-repo branches, approval for forks. Two mechanisms, both auditable:

- a `hardware-lab` GitHub Environment with required reviewers — the job literally pauses until a maintainer clicks approve, and the approval is logged
- a `safe-to-hil` label as a secondary signal, **auto-removed on every new push** by a tiny `pull_request.synchronize` workflow, so a contributor can't get a clean diff approved and then push a dirty one

Belt and braces, but the label alone is not enough — label state and head SHA can desync — and the environment gate alone gives no signal on the PR itself.

**Reporting.** `workflow_run` jobs have write permissions, so the result is posted as a check run keyed to the PR's head SHA via the Checks API. That's what makes it eligible to be a required check later.

---

## 5. Physical and network layout

### Runner host

The existing Pi already runs the Actions runner with a USB hub attached, so the hardware question is largely settled. Worth noting for the record: **that Pi is a Zero 2 W, not a Zero 1 W.** The GitHub Actions runner ships only for Linux x64, ARM64, and ARM32 (ARMv7); the original Zero/Zero W is ARMv6 (`ARM1176`) and the runner will not start on it at all. A runner that runs is a Zero 2 W (Cortex-A53). No need to verify further — it's proven by the fact that it works.

Constraints to design around on that hardware:

- **512 MB RAM** shared between the runner, Python, and three concurrent `mpremote` sessions. Workable, but keep per-board test processes lean and avoid loading whole build trees into memory. Swapping to the SD card will hurt badly and will show up as timing flake.
- **Single-core-ish throughput.** Board work is I/O-bound on serial round-trips rather than CPU-bound, which is what makes 3-way parallelism viable at all — but orchestration overhead is not free at this scale.
- **USB hub already present.** Confirm it is self-powered; three Picos plus enumeration churn on a Zero 2 W's OTG port is more than the bus-powered case wants to supply.

If the combined per-PR matrix (§8) turns out too slow, the first thing to try is more boards rather than a bigger Pi — the work is serial-I/O-bound, not compute-bound, so a faster host buys much less than a second WPC board does.

### Board network

Boards live on a dedicated VLAN. Rules:

- **Allow:** board subnet → Pi's HTTP file server (serves update packages for OTA tests).
- **Allow:** intra-VLAN broadcast, so `discovery.py` peer discovery is actually exercised.
- **Deny:** board subnet → rest of the LAN.
- **Deny:** board subnet → internet.
- The Pi needs an interface on the VLAN (tagged sub-interface on a USB ethernet adapter, or a second SSID) *plus* uplink to github.com.
- Firewall the runner from the rest of the LAN too. It is a CI box that pulls untrusted artifacts; it is not a trusted host.

One wrinkle: `/api/update/check` fetches `http://software.warpedpinball.com/vector/<system>/latest.json` (`src/*/systemConfig.py:2`). Rather than punching an egress hole, **override that hostname in DNS on the VLAN to point at the Pi** and serve a canned `latest.json`. That keeps egress at zero and makes the update-check test deterministic — you can assert behavior against a pinned "latest" instead of whatever is live.

### Board addressing

`/dev/ttyACM*` ordering is not stable across reboots or re-enumeration. Use udev rules keyed on each Pico's unique USB serial number to get stable paths:

```
/dev/vector-sys11-a
/dev/vector-wpc-a
/dev/vector-data-east-a
```

Static DHCP leases on the VLAN, keyed by MAC, for the HTTP side.

---

## 6. Bench manifest

The inventory is going to grow (`em`, `whitestar`, `classic`, and probably a second WPC board). Nothing about board count or identity should be hardcoded.

`dev/hil/bench.example.yaml` in the repo; the real one at `/etc/vector-hil/bench.yaml` on the Pi, located via `$VECTOR_HIL_BENCH`.

```yaml
boards:
  - id: sys11-a
    target: sys11              # matches an id in dev/ci/targets.json
    hardware: sys11            # build tree to flash
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
secrets_file: /etc/vector-hil/secrets.yaml   # game password, wifi creds
```

Tests parameterize over `manifest ∩ dev/ci/targets.json`. Adding `whitestar` later is a udev rule plus three lines of YAML — no test changes. Multiple boards with the same `target` are treated as a pool and sharded across, which is how you buy throughput later.

`sys11_tiny` is the same hardware as `sys11`, so it runs as a second firmware pass on the `sys11-a` board rather than needing its own.

---

## 7. Harness structure

### One workflow, three stages

`.github/workflows/hil.yml` is the whole bench. It replaced four separate
workflows that shared the `hil-bench` concurrency group — and since GitHub keeps
only one *pending* run per group, a push touching two of them had them race with
the loser silently cancelled. One workflow takes one lease and runs:

| stage | what it is | cost |
|---|---|---|
| recover | `recover.py` — repair any wedged board | ~30s healthy |
| flash + health check | G1/G2, API over USB *and* HTTP | ~3.5 min |
| config matrix | G3, every config on every board | ~45 min |

Every stage runs even when an earlier one fails, and the verdict is taken at the
end: one broken board should not cost the signal from the others. Running
recovery first is the point of combining them — it costs almost nothing on a
healthy bench and turns "a board wedged, so the next four runs were useless"
into a bench that repairs itself.

### What "the bench is here" means

Three states have to be told apart before any of the above is worth running, and
getting them confused has cost whole runs:

- **On serial.** The normal case: a port, a chip id, a system it reports running.
- **In BOOTSEL.** No serial port at all — the ROM bootloader enumerates as USB
  mass storage, so `mpremote devs` is empty while `lsusb` lists every board.
  This looked exactly like an unplugged bench and was reported as "no boards
  found — check the USB hub and power" for a bench that was fine. The bootrom
  publishes the board's unique id as its USB serial number, which is the same id
  `machine.unique_id()` returns, so these boards are identifiable through
  `VECTOR_HIL_BOARD_MAP` like any other: the harness mounts the drive and writes
  the pinned TrenchCoat UF2 for the mapped target, and the board rejoins the run.
- **Absent.** Not enumerated either way. This is the state that must fail the
  run rather than shrink it: two boards out of three passing is a green run that
  proves nothing about the third. `REQUIRED_TARGETS` names the systems the bench
  is for; `VECTOR_HIL_REQUIRED_TARGETS` on the runner is how a bench that has
  really lost a board says so out loud.

A board whose chip id is in none of the map's entries is never guessed at — the
id and the exact line to add are written to the job summary, because the fix is
one edit on the runner host and whoever makes it is reading the run, not the log.

Boards are flashed concurrently. They are independent devices on independent
ports and `dev/flash.py` is one subprocess each, spending nearly all of its time
waiting on USB, so the stage costs about what one board costs instead of three.
The failure output travels with the exception rather than being printed by the
worker, so a failing board's log is still that board's log.

**Trigger: `workflow_run` on "Build and Deploy" completion**, which is every
push to a PR. Not `pull_request`, and the distinction is the security model:
`workflow_run` workflows always run *from the default branch, using the default
branch's code*, so a PR cannot change the workflow, `dev/hil/**`, or the pinned
dependencies that the Pi executes. The bench job checks out the default branch
and then takes **only `src/`** from the commit under test, so the firmware is
the PR's and the harness is not.

Fork PRs are gated: the `gate` job stops them with a message saying to review
and dispatch by hand. Making forks automatic-with-approval needs a
`hardware-lab` Environment with required reviewers (§4) — a repository setting,
not something the workflow can create.

What exists today:

```
dev/hil/
  bench.py               # shared plumbing: inventory, resolve, build, flash,
                         #   reset, wait-for-boot, USB request, config select
  flash_and_check.py     # G1/G2: one flash per board, then the API health
                         #   check over both USB and HTTP
  config_matrix.py       # G3: one flash per board, then every game config for
                         #   that target in turn
  setup-runner.sh        # bench Pi provisioning
  DESIGN.md, RUNNER_SETUP.md
```

`bench.py` deliberately asserts nothing about firmware behaviour — it only gets
a board into a known state and talks to it, including driving the raw REPL over
a connection the caller owns (`bench.Repl`) rather than shelling out to
`mpremote`. Assertions live in the harness that
imports it, so adding a check never means touching the plumbing. The
hardware-free parts (config discovery, selection and ordering, and each
assertion with the board faked out) are covered by
`dev/tests/test_hil_config_matrix.py`.

The originally proposed structure, for reference — pytest-driven, with a
manifest and a board pool. Worth revisiting when a second board of the same
target arrives and sharding starts to matter:

```
dev/hil/
  bench.py               # manifest load + validation
  board.py               # Board: transports, reset, wait_for_boot, flash, seed_config
  transports/
    usb.py               # JSON-over-serial client for usb_comms.py
    http.py              # HTTP client with challenge/HMAC auth
  flashing.py            # wipe + mpremote fs cp from a build tree; OTA via /api/update/apply
  update_server.py       # local HTTP server for OTA payloads
  conftest.py            # fixtures: board pool, per-test lease, artifact discovery
  tests/
    test_boot.py
    test_api_contract.py
    test_configs.py
    test_update_matrix.py
  bench.example.yaml
  README.md
```

### Two transports, and an important asymmetry

Vector exposes the same routes over HTTP (phew) and over USB serial (`usb_comms.py` replays into `phew.server._routes`). Running tests over both catches regressions in either bridge.

But note `backend.py:280-287`: **the USB transport bypasses authentication entirely.** Requests tagged `is_usb_transport` skip the HMAC check. Two consequences:

- **Auth tests must run over HTTP.** Over USB every route is reachable unauthenticated, so USB can't tell you anything about the auth layer.
- **USB is a convenient privileged setup channel.** Seeding config, scores, and adjustment profiles for a test doesn't need credentials at all — just drive it over serial. That simplifies fixtures considerably.

The HTTP client mirrors `src/common/web/js/utils.js:64-72`: `GET /api/auth/challenge`, then `hmac_sha256(password, challenge + path + query + body)` hex-encoded into `X-Auth-HMAC`, with the challenge in `X-Auth-challenge`.

---

## 8. Test design

### G1 — boots and runs normally

Per board, per target firmware: wipe → flash build tree via `mpremote` → seed bench config → `machine.reset()` → capture serial console.

Assertions:

- Banner and `Version <expected>` on the console within the timeout
- `/api/version` matches the version built from the PR head SHA
- `/api/fault` contains only bench-expected faults (see below)
- No `SFTW01` (drop-through) — that fault means `backend.go()` returned, which it never should
- **Soak, 60–120s:** poll `/api/memory-snapshot` and `/api/game/status`. Assert free memory doesn't trend toward zero and the scheduler still answers. This catches `SFTW02: async loop interrupted` and slow leaks, which are exactly the failures a single boot check misses.
- `/api/wifi/status` connected with the expected IP; `/api/network/peers` sees the other bench boards (exercises `discovery.py`)

#### ⚠️ Bare-board boot behavior — characterize this first

This is the most likely source of a flaky suite, and it needs measuring during bring-up before any test is written.

`main.py:44-66` runs `bus_activity_fault_check()`: it samples GPIO14–21 (the data lines) for 800 ms and raises **`HDWR01: Early Bus Activity`** if it counts more than 250 transitions. On a bare board those eight pins are floating inputs. If they pick up enough noise to cross the threshold, the board takes a completely different boot path — `GameDefsLoad.go(safe_mode=True)`, `MemoryMain` skipped, error LED — and every downstream assertion changes meaning.

Separately, `adr_activity_ok()` raises **`HDWR02: No Bus Activity`** when shadow RAM lamp columns don't change, which on a bare board is the correct and permanent state.

**Measured on the bench (2026-08-17), and both predictions were wrong:**

- `HDWR01` did **not** fire. Three boards, freshly flashed for their real targets, all booted
  with `faults: none`. The floating-pin worry did not materialise — no resistor pack needed,
  and the config assertions are not silently vacuous.
- `HDWR02` did not fire either, and cannot: **`adr_activity_ok()` is defined but never called**
  (`src/common/main.py:69`, `src/data_east/main.py:82`). The fault is unreachable code.

That second point is a finding about the firmware rather than the bench. `HDWR02: No Bus
Activity` is exactly the diagnostic a customer with a dead bus needs, and today nothing can
raise it. Worth a separate issue: either wire the check into the boot path or drop the fault
code, but leaving a dead diagnostic in `faults.py` is the worst of both.

The allowlist keeps tolerating `HDWR02` for now — harmless, and it costs nothing if the check
is ever reconnected. `HDWR01` stays a warning that suppresses the active-config assertion,
since if it ever does fire the board is in safe mode and the config genuinely was not loaded.

Bring-up task: boot each bare board 50 times, record the fault set each time, and confirm it is identical every time. Until that holds, nothing else is worth automating.

### G2 — connect and hit the API

**Generated contract tests.** `tools/gen_api_docs.py` already parses the `@api` docstrings out of `backend.py`. Reuse that parser as the test inventory rather than hand-maintaining a list:

- every documented unauthenticated route returns 200 and parseable JSON whose top-level shape matches the documented example
- every `auth: true` route returns 401 over HTTP without credentials, and succeeds with them
- **every route the server actually registers is documented** — walk `phew.server._routes` over the REPL and diff against the parsed docs

That last one is the valuable one. It turns the API docs into a load-bearing artifact and makes "shipped an undocumented endpoint" a build failure instead of a discovery.

**Auth behavior** (HTTP only): wrong password rejected; a replayed challenge rejected (`backend.py` deletes the challenge on use — worth a regression test); expired challenge rejected; more than 10 outstanding challenges returns 429.

**Round-trip state:** set an adjustment profile name → read back; import scores → export → compare; set tournament mode → reset → still set (proves FRAM persistence, which is what update tests depend on later).

**Static serving:** `/`, `/index.html`, gzip `Content-Encoding`, and the ETag/304 path.

**Known gap:** AP-mode setup can't be tested. `check_ap_button()` reads GPIO22, and with software-only control we can't hold it. One wire per board from GPIO22 to a Pi GPIO would unlock it; worth doing only if AP-mode regressions start to bite.

### G3 — every config parses and boots

**Implemented** in `dev/hil/config_matrix.py`, run as a stage of `.github/workflows/hil.yml`.

Per board: build and flash that board's target once, so the config bundle under
test is the one this checkout produces, then loop over every config in
`src/<target>/config/`:

1. Write `gamename` into the `SPI_DataStore` `configuration` record over the REPL, and **read it back** — see the fixed-width field note below
2. `machine.reset()`, then wait for the ready marker on the console
3. Assert:
   - no `CONF00` / `CONF01` fault, and no `HDWR01` either — `HDWR01` puts `main.py` down the `safe_mode` path where the config is never read at all, so it is fatal here even though `flash_and_check.py` only warns about it
   - `/api/game/active_config` is the config we set
   - `/api/game/name` matches `GameInfo.GameName` **from the source JSON in the repo** — this cross-checks the on-board `config/all.jsonl.z` against the source and catches build-time config-packing bugs, not just parse errors
   - `/api/leaders` and `/api/adjustments/status` both return 200 — proves the parsed definition is *usable*, not merely loadable

Each board's bundle is also compared against the source directory once, before
the loop: same set of config names, same game names. That localises a packing
bug to one boot instead of one boot per affected config.

**Why the game name is the load-bearing assertion.** A config that fails to
apply does not fault or crash from the outside: `GameDefsLoad.go` falls back to
`safe_defaults` and the board serves a generic definition for its hardware,
healthy in every other respect. `/api/game/active_config` does not catch this —
it reads the `gamename` field back out of FRAM, not what actually loaded. The
game name is what separates "loaded my config" from "silently fell back".

#### Bench results, first full run

sys11 passed all 39 of its configs, at 20–22s each (~14 min). That is the
harness working end to end: set the config, reboot, and confirm the board comes
up reporting that game.

WPC did not, and the reason is worth recording because it shaped the design.
The board wedged — silent console, no reply to Ctrl-C — on the first handoff
from our serial connection to `mpremote`, and stayed wedged for the remaining
62 configs. The Pico has a single CDC endpoint, so using `mpremote` mid-run
meant closing our connection, letting a second process open the port, and
reopening afterwards, once per config. sys11 (MicroPython v1.24.1) survived
that 39 times; WPC (v1.26.0-preview) did not survive it once. A running board
printing into a CDC endpoint that nothing is draining is the difference between
them.

So the harness now **never hands the port to another process and never leaves
it unread while the board is running.** The REPL is driven directly over the
connection the harness already holds (`bench.Repl`), and the port is closed
only while the board is mid-reset. Three further changes came out of the same
run:

- **Two consecutive setup failures abandon the board.** The first run spent 63
  minutes writing the same 60s timeout 63 times. A board that stops answering
  does not start again on its own.
- **Teardown cannot fail the run.** A `TimeoutExpired` escaped `restore_default`
  and took the whole process down with a traceback — losing the summary and
  skipping data_east, which had never been touched.
- **`stty raw -echo` before dumping a console.** A tty reverts to ECHO-on once
  every handle closes, so the `cat /dev/ttyACM*` diagnostic step was echoing
  each board's output back into it; the logs show all three boards parsing
  their own log lines as USB API requests. Fixed in both HIL workflows.

#### Why boards are flashed one at a time

Flashing every board up front and then working through them in turn is the
obvious ordering, and it is wrong. A board flashed first and used last spends
however long the boards ahead of it take — half an hour on a full run — running
the application and printing `SCORE:` / `RESOURCE:` / `DISCOVERY:` lines into a
USB CDC console that nothing is draining. TrenchCoat documents where that ends
(`src/ray.py`, `send_command`):

> if nothing ever drains the board's output, the USB CDC buffers fill up,
> MicroPython blocks writing to stdout, and the board deadlocks mid-script

That is not hypothetical. It killed `data_east` 36 minutes into a run — the
board simply stopped answering `mpremote` — and it is the most likely
explanation for the WPC board that went silent for an hour on the very first
bench run and needed recovering.

So each board is flashed immediately before its own matrix. Boards waiting
their turn sit at the REPL, where inventory's probe leaves them, producing no
output at all. Builds still happen up front; they touch no hardware.

As a second line, a board that will not take a reset gets its console drained
and one retry: reading is the remedy for exactly this deadlock and costs
seconds, against writing off a whole board's matrix.

#### Draining reads until the board goes quiet, not for a fixed few seconds

A blocked board does not hand its backlog over in one gulp. It unblocks, runs
a little further, prints some more, and only then falls silent — so a drain
with a fixed three-second budget catches the first mouthful and declares the
board dead. That is measured, not argued: one bench run wrote off
`/dev/ttyACM0` as unrecoverable after draining 63 bytes from it, and the very
next step in the same job read the port with `cat` for eight seconds and got a
healthy, running web server.

So `bench.read_until_quiet` reads until the port has been silent for a couple
of seconds, capped at a budget. A port with nothing to say costs the quiet
period; one with a backlog gets as long as it needs. The Ctrl-C comes *after*
the drain, because a firmware blocked writing to stdout is not reading stdin
either — the host's OUT endpoint backs up too, so writing first only times out
against the wedge it is trying to clear. A timed-out interrupt is likewise a
reason to read more and try again, not a reason to give up.

This matters more than it sounds: on the current runner the drain is the only
recovery rung that can always be reached. The USB reset needs a udev rule and
the power cycle needs `uhubctl`, and neither is installed (see
RUNNER_SETUP.md), so everything above the drain escalates straight to a flash
wipe.

What the two directions did is then the diagnosis, and they point at different
remedies. Bytes read but the Ctrl-C refused means the board is *talking but not
listening*: producing output normally and never servicing what we send it, so
no amount of reading reaches it — that is what the USB reset and power cycle
rungs are for, and with both unavailable there is genuinely nothing left to
try. Nothing read at all is the opposite: not a board blocked on a full output
buffer, because such a board has a backlog to give up the moment somebody
reads. Both are reported in those words rather than as "still dead", which sent
a maintainer looking for a bricked Pico when the board in question was running
the application and printing to its console the whole time.

#### A lost connection is repaired, not treated as a verdict

If a board's boot fails outright, the session is left holding no connection,
and without care every config after it fails instantly with "the board is not
connected" — including the retry that exists precisely to survive a flaky
board. The bench showed the exact shape: the WPC board crashed on boot twice
for one config, and from there the retry failed in no time at all and the next
config failed in 0.0s, two configs blamed on a board that came back on its own
moments later and served the restore step happily.

So `Session.ensure_connected()` runs before each attempt: if there is no live
connection it drains, resets, and watches the board come up. A board that is
genuinely gone still ends its own matrix through the consecutive-failure
counter; this only stops that happening while the board is still recoverable.

#### One reset per boot

`dev/flash.py` ends by resetting the board, so a freshly flashed board is
already booting. Resetting it again lands on top of that boot, while the
firmware is still reading a filesystem written seconds ago — and sys11 wedged
in exactly that window: flashed successfully, then refusing a reset and any
console traffic seconds later. `Session.start(reset=False)` watches the boot
that flashing started instead of forcing another. It is the same shape as the
`ENOENT`-on-a-file-that-exists crashes WPC raises, and suggests both are the
firmware being disturbed while it reads freshly written flash.

#### Telling a broken config from a flaky board

They produce the identical symptom on one attempt and need opposite responses,
so every failing config is retried once. Fails twice → the config, and the run
goes red. Passes on the retry → the board, recorded as a **flake** against that
board and reported in the summary, without blaming the config.

This is not hypothetical either. The WPC board raises `ENOENT` mid-boot on files
that plainly exist; a board that will do that to an import will do it to a route,
and a run where `Congo_21` failed `/api/leaders` with a 500 and `Theatre_13`
failed `/api/adjustments/status` the same way — on a board that also crashed
once on boot in the same run — is exactly the ambiguity this resolves. Without
the retry those read as two broken configs, which would be the wrong conclusion
and would erode trust in the check.

#### How a boot is watched

The ready marker (`Server: Loop Forever`) is printed exactly once per boot, which
makes watching for it precise but brittle in two directions. Both are handled:

- **The board crashes instead of coming up.** MicroPython prints a traceback and
  drops to the REPL; nothing will ever print the marker. The watcher recognises
  the REPL banner and fails immediately *with the traceback*, rather than burning
  the timeout and reporting "never reported its web server" — which is what
  happened on the first full bench run and buried the real cause. A crash is
  retried once, because it can be intermittent and losing a whole board's matrix
  to one flaky boot buys nothing; every crash is counted and reported in the run
  summary either way, so a board that only sometimes boots never reads as clean.
- **The marker goes past before we are watching.** Any boot we did not trigger
  ourselves looks identical to a board that never came up. On timeout the watcher
  asks the board over the USB API before failing: a board that answers is up,
  whatever we did or did not see, and says so as a warning.

Timeouts are set from measurement, not guesswork. Across 70 boots on the bench:
**11.8s minimum, 15.5s mean, 25.6s maximum.** The matrix allows 90s and the flash
harness 150s, so neither is close to marginal — a boot that exceeds them has
stopped, not slowed.

#### Findings and limits

- **~~Two WPC configs cannot be selected at all.~~ Fixed in #380.** The bench's
  first real finding: `configuration.gamename` is a 16-byte fixed-width field
  and `struct.pack` truncates silently, so `HarleyDavidson_L3` and
  `GilliganIsland_L9` at 17 characters were offered by the web UI, accepted on
  write, truncated into FRAM, and matched nothing on the next boot — `CONF01`,
  safe defaults, and a game that could never be selected. Shortened to
  `HarleyDavid_L3` and `GilliganIsle_L9`. `test_no_config_name_exceeds_the_gamename_field`
  now enforces the rule absolutely, with no allowlist.
- **WPC boots intermittently fail on a missing file.** Four crashes in one
  63-config run, in two flavours — `ImportError: no module named 'origin'` and
  `OSError: [Errno 2] ENOENT` — both raised from `phew/server.py:create_schedule`
  during boot. Both are "file not found", on files that plainly exist: the same
  board boots fine on the retry every time. That points at the on-board
  filesystem returning ENOENT under some condition, not at the config bundle and
  not (as first guessed) at memory pressure. A `nuke.uf2` wipe before reflashing,
  which is what `recover.py`'s reflash rung does, is the obvious thing to try
  next: if the littlefs on that board is degraded, it would clear it.
- **`/api/adjustments/status` 500s for configs with no `Adjustments` section.**
  `GameDefsLoad` assigns the parsed config straight to `SharedState.gdata`
  without merging `safe_defaults` into it, so the key is simply absent and
  `Adjustments._get_range_from_gamedef` raises `KeyError`. 14 shipped configs
  are affected. Warned about rather than failed, so that a firmware gap the
  harness cannot fix does not bury the signal it exists for.
- **Configs that share a `GameName` are not distinguished from each other.**
  The four `AddamsFam_*` variants all report "Addams Family", and no route
  exposes anything else from `gdata`. For those, a pass means "this config
  parsed and loaded without faulting", not "this exact ROM revision's
  definition is in memory".
- **The free-memory floor is not implemented.** No route reports heap, and
  reading `gc.mem_free()` over the REPL means interrupting the running
  firmware, which ends the boot being measured. `sys11_tiny` exists because RAM
  is tight, so this assertion is still worth having — it needs a small
  firmware-side route first.

**Throughput.** Measured on the bench, per board, from the flash/health-check harness:

| Stage | sys11 | wpc | data_east |
|---|---|---|---|
| build | 13.7s | 21.7s | 19.8s |
| flash (wipe + copy + config + reset) | 26.4s | 28.0s | 22.5s |
| boot → API answering + full health check | 11.7s | 14.8s | 10.7s |

So a full flash-and-verify of all three boards is **~3.5 min end to end**, and build cost is
not a concern on the Zero 2 W — the caching this design worried about is unnecessary.

The number that drives the config matrix is the last row: a board answers its API within
roughly 10s of reset, and the health check itself accounts for most of that 10–15s. The
15–25s per-config estimate below therefore still holds, but is an estimate — a per-config
reboot loop has not been measured yet.

Boot cycle is roughly 15–25s (`main.py` alone has an 0.8s bus check plus ~4.5s of sleeps
before WiFi comes up), times config count:

| Board | Configs | Serial estimate |
|---|---|---|
| wpc | 63 | ~16–26 min |
| sys11 | 39 | ~10–16 min |
| data_east | 28 | ~7–12 min |
| em | 1 | trivial |

Boards run in parallel, so wall clock ≈ the WPC leg, **~16–26 min per PR**. That's a real cost and the bench is a singleton. Recommended mitigations:

- `concurrency: { group: hil-bench, cancel-in-progress: false }` — queue, don't interleave. Two jobs sharing one bench will corrupt each other's state.
- Path filters so docs-only and workflow-only PRs skip HIL entirely.
- Order the loop so configs touched by the diff run first — fail fast on the likely culprit.
- Poll readiness over **USB rather than HTTP**; the USB bridge is answering well before WiFi associates, which shaves seconds off every one of 130 iterations.
- When it gets annoying, add a second WPC board. The manifest already supports pools, and the runner shards across them — that alone roughly halves wall clock.

### G4 — update from the last 5 versions

Matrix: each board target × the last 5 **stable** releases. Note the release list is mostly prereleases (`1.11.28-beta1746` etc. are PR builds); filter to `prerelease == false`, which currently gives `1.11.28`, `1.11.27`, and so on.

Getting a board *to* an old version is the interesting part. Rather than building historical source — which drags in period-correct `mpy-cross` and MicroPython versions and is genuinely painful:

1. Flash the current build once.
2. Apply version *V*'s **signed** release asset via `/api/update/apply` with no skip flag. This gets us to V using the real OTA mechanism, and as a bonus exercises the *signed* code path on the way down.
3. Confirm `/api/version == V`.

Caveat worth stating: that's a downgrade, which no user performs. But the resulting filesystem is exactly what V's update package produces, which is what the upgrade is going to be applied to — so the fidelity that matters is preserved.

Then the actual test:

4. Seed realistic state — scores, players, adjustment profiles, settings. `dev/test_data.json` already exists for this and `flash.py --test-data` already knows how to write it.
5. Serve the PR's `<target>-update.json` from the Pi.
6. `POST /api/update/apply` with `skip_signature_check: true`. Consume the streamed progress JSON; assert percent is monotonic and no error lines appear.
7. After reboot, assert:
   - version == the PR version
   - **all seeded state survived** — scores, players, adjustments, tournament mode, claim methods, WiFi credentials, gamename. Data migration is the real risk in an upgrade, and it's invisible to a version check.
   - no faults, API healthy, free memory sane
   - **no stale files** — the update runs a `remove_extra_files.py` execute-step, so diff an `ls` over the REPL against the expected build tree. A file the cleanup misses is a file that shadows a module in a later version.

#### Negative tests

The update path is the most security-sensitive code we ship, and these are cheap:

- unsigned PR package applied **without** `skip_signature_check` → must be rejected, **and the board must still boot afterward**
- one byte flipped in the body (hash mismatch) → rejected
- valid hash, garbage signature → rejected
- **interrupted mid-update** — reset the board at ~50% and see what happens. This is the "user pulled the plug" scenario. Either it recovers to something bootable, or we learn precisely how it fails and how to talk a customer through it. Right now nobody knows which.

The negative tests are what buy back the coverage lost by using `skip_signature_check` for the happy path.

#### Additional cases worth having, given updates are the suspected problem area

- **Repeated updates in one power cycle.** Apply an update, then apply another without a power cycle in between. `apply_update()` runs inside `LowMemoryMode`, which halts the phew scheduler and closes the discovery sockets on entry and rebuilds them on exit (`update.py:157-196`). If `__exit__` doesn't fully restore that state, the second update is where it shows. Field users do sometimes update twice in a row.
- **Chained vs. direct upgrades.** The common case is a direct jump from an old version to the newest, and that's what the main matrix covers. A chained walk (V-5 → V-4 → … → proposed) additionally catches migration-ordering bugs, where each individual hop works but the sequence doesn't. Worth running on release tags even if it's too slow for every PR.
- **Bytecode compatibility (see the toolchain note below).** After an update, assert every `.mpy` on the board actually imports. A bytecode-version mismatch produces a board that updates "successfully" and then fails to boot — which looks exactly like a mysterious update bug.

#### ⚠️ Toolchain finding: `mpy-cross` was unpinned

Worth surfacing here because it lands squarely in the "we suspect there might be issues with updates" category.

`dev/requirements.txt` pinned `mpremote==1.23.0` but left **`mpy-cross` unpinned**, so CI resolved whatever was newest — currently `1.28.0.post2`. Meanwhile the MicroPython in the shipped UF2s is not uniform:

| Firmware | MicroPython |
|---|---|
| `Vector_WPC_v5.uf2` | v1.26.0-preview.255 |
| `Vector_DataEast_v1.uf2` | v1.26.0-preview.255 |
| `vector_system_11_and_9_v4.uf2` | v1.24.1 |

`.mpy` files carry a bytecode version in their header, and a board's MicroPython refuses to import a `.mpy` whose version it doesn't know. So the build was compiling bytecode with a 1.28 toolchain and shipping it to firmware three to four minor versions behind, with nothing asserting the pairing is valid.

It happens to work today — verified empirically that `mpy-cross` 1.23.0 and 1.28.0.post2 both emit `mpy_version=6, flags=0x00`, and a full `sys11` build produces 41 `.mpy` files all at version 6. So this is not a live bug. But it is unpinned, undocumented, and load-bearing: the day `mpy-cross` bumps to bytecode version 7, every build silently produces modules that no deployed board can import, and every OTA update bricks on the next boot. That failure would be very hard to diagnose from the symptom.

`mpy-cross` is now pinned to `1.28.0.post2` — deliberately the version CI was already resolving, so the pin freezes current behavior rather than changing it. **The open question is what it *should* be pinned to**, which is a hardware question we can't answer from the repo: it should match the MicroPython in each target's UF2, and today those differ per target while the build uses one toolchain for all of them. See §12.

This is also the single best argument for the update matrix running on every PR: it's exactly the class of problem where the build is green, the unit tests pass, and only real hardware tells you.

**Runtime:** 5 versions × 3 boards, ~3–5 min each (two OTA cycles plus verification), parallel across board types → ~20–25 min for the upgrade matrix alone.

**Combined per-PR cost.** G3 and G4 contend for the same physical boards, so they serialize per board rather than overlapping. The WPC board is the critical path both times:

| | wpc board | sys11 board | data_east board |
|---|---|---|---|
| Config matrix (G3) | ~16–26 min | ~10–16 min | ~7–12 min |
| Upgrade matrix (G4) | ~15–25 min | ~15–25 min | ~15–25 min |
| **Serial total** | **~31–51 min** | ~25–41 min | ~22–37 min |

So expect **roughly 30–50 minutes of bench occupancy per PR**, on a singleton bench, with PRs queueing behind each other. That is the accepted cost of treating updates as critical infrastructure. Levers, in the order worth reaching for:

1. **Run G4 first.** The most valuable signal arrives earliest, and a broken update fails the run before spending 26 minutes on configs.
2. **A second WPC board.** Config matrix on board A, upgrade matrix on board B, genuinely in parallel — cuts the critical path from ~51 to ~26 min. This is the highest-leverage purchase on the whole bench and the manifest already supports pools.
3. **Path filters.** Docs-only and workflow-only PRs skip HIL entirely.
4. **Poll readiness over USB, not HTTP** — saves seconds on every one of ~180 boot cycles per run.
5. If it still hurts: move the *chained* upgrade walk to release tags and keep only direct jumps per PR.

---

## 9. Runner hardening checklist

- **Ephemeral runner** (`--ephemeral`), registered at repo scope, label `vector-hil` — *not yet
  done; the bench currently runs a persistent runner. Ephemeral registration needs a PAT with
  `administration: write` stored on the Pi to mint a token per job, which is a worse secret to
  hold than the runner's own credentials. Acceptable only because `workflow_run` means the Pi
  never executes PR-authored code; see RUNNER_SETUP.md for the full reasoning.*
- Unprivileged user, no sudo, no docker socket
- `ACTIONS_RUNNER_HOOK_JOB_STARTED` / `_COMPLETED`: wipe `_work/`, run a bench-health precheck (all boards enumerate and answer), fail the job immediately if the bench is unhealthy rather than producing a confusing test failure
- **No secrets on any self-hosted job.** In particular `WARPED_PINBALL_PRIVATE_KEY` must never be referenced by a job with a `self-hosted` label. Move signing into a dedicated environment restricted to `main` and tags so it is structurally unreachable from HIL.
- Repo setting: Actions → *Require approval for all outside collaborators* at minimum
- Minimal `permissions:` per job — HIL needs `checks: write`, `actions: read`, `contents: read`, nothing more
- Egress firewall on the Pi: github.com / api.github.com / objects.githubusercontent.com plus package mirrors; deny lateral movement into the LAN
- ~~**Pin actions by SHA.**~~ **Done in this PR.** All six workflows now pin every action to a commit SHA with the version in a trailing comment, and `dev/requirements.txt` pins every Python dependency. Previously `deploy_docs.yml`, `docs-on-pr.yml`, `specialfeatures-on-pr.yml`, `validate-json-configs.yml`, and `version-bump-guard.yml` used floating `@v4`/`@v5` tags — a compromised or repointed tag on any of them is a path to the same runner the bench will be attached to. Keep this invariant: **no floating tags, ever**, and consider a CI check that greps for `uses:.*@v[0-9]` to enforce it.
- `timeout-minutes` on every job, sized just above the measured worst case

## 10. Risk register

**Software-only reset means a wedged board stops the bench.** A PR — malicious or just buggy — can leave a board where `mpremote` can't reach the REPL: a `boot.py` that hard-faults, a tight loop blocking the USB REPL, or a corrupted filesystem. With no BOOTSEL control, recovery needs someone physically present. The config matrix touches every board on every PR, so the exposure is not hypothetical.

Mitigations that cost nothing:

- bench-health precheck that fails loudly, and optionally opens an issue, rather than timing out mysteriously
- a documented recovery runbook — `trench-coat/uf2/nuke.uf2` plus a UF2 reflash is the escape hatch
- tight `timeout-minutes` so a hung board doesn't burn an hour of queue

Worth revisiting after a month: a `uhubctl`-capable powered hub plus BOOTSEL and RUN wired to Pi GPIO (2 pins per board) turns "walk over and press a button" into a test step, for roughly $20. If the bench wedges more than once or twice, buy the hardware.

Note that `machine.reset()` is a full MCU reset, so `boot.py` and `main.py` do run — the boot-path coverage loss is small. What's genuinely not covered is cold-power-on and brown-out behavior, and FRAM state at power-up.

**Other risks:**

| Risk | Mitigation |
|---|---|
| `HDWR01` fires nondeterministically on bare boards | Characterize during bring-up; add a resistor pack if needed (§8, G1) |
| Bench is a singleton; PRs queue | Concurrency group, path filters, add boards as needed |
| Fork PR approved clean, then pushes dirty | Label auto-removed on `synchronize`; environment gate is per-run |
| Harness rots as API changes | Contract tests generated from `@api` docstrings fail when routes drift |
| Flaky HIL erodes trust in CI | Keep it non-blocking until measured flake rate is under ~1% over a week |
| `mpy-cross` bytecode version drifts away from shipped firmware | Now pinned; add a post-update HIL assertion that every `.mpy` imports (§8, G4) |
| ~30–50 min per-PR bench occupancy on a singleton bench | Run G4 first, path filters, second WPC board when it bites (§8) |
| 512 MB RAM on the Zero 2 W under 3-way parallelism | Keep test processes lean; watch for swap-induced timing flake |

## 11. Rollout

| Phase | Work | Exit criteria |
|---|---|---|
| 0 | Pi, VLAN, udev rules, 3 boards. Characterize bare-board fault behavior. Measure reset→ready. | 50 consecutive boots produce an identical fault set |
| 1 | `dev/hil` package, boot smoke test, `workflow_dispatch` only | Green run driven by hand |
| 2 | API contract tests over both transports. `workflow_run` trigger on, auto for maintainer branches, fork gate live. Non-blocking check. | Contract tests catch a deliberately broken route |
| 3 | **Upgrade matrix, every PR.** Promoted ahead of the config matrix — it's the highest-value signal and the suspected problem area. | Full 5-version matrix green across all three boards |
| 4 | Full config matrix | Combined run under ~50 min; flake rate under 1% over a week → make it a required check |
| 5 | Expand manifest to `em`, `whitestar`, `classic`; second WPC board to parallelize G3 against G4 | — |

Phases 0 and 1 are where the real uncertainty lives. Everything after that is mostly typing.

Note that phases 3 and 4 are deliberately ordered opposite to the goal numbering. The update path is the reason this bench exists, so it should be the first thing running on every PR — the config matrix is more coverage but less risk per unit of wall clock.

## 12. Open questions

1. **What should `mpy-cross` be pinned to?** It's now frozen at `1.28.0.post2` (what CI already resolved), but the shipped UF2s carry MicroPython v1.24.1 for System 11/9 and v1.26.0-preview for WPC and Data East. Ideally the build toolchain matches the target's firmware, which today would mean a per-target `mpy-cross` rather than one for all of them. Needs a hardware decision: standardize the firmware across targets, or make the build toolchain per-target. See §8.
2. **Bench WiFi credentials** — does the VLAN get its own SSID, or do boards join the existing one with VLAN assignment by MAC?
3. **Should HIL be a required check?** Recommendation: yes for G1–G4 once the flake rate is measured over a week. With G4 running per-PR by design, making it advisory-only would waste most of its value.
4. **How many versions back do we actually support?** The design says 5 stable releases; if the real support window is different, that's a one-line change to the matrix.
5. **Do we want a `latest.json` fixture served from the Pi** to make `/api/update/check` testable, or leave that endpoint untested?
6. **Is the existing USB hub self-powered?** Three Picos on a Zero 2 W's OTG port wants a powered hub.
