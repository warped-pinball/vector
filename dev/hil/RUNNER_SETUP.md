# HIL Bench — Pi Runner Setup

Sets up a Raspberry Pi with Vector boards attached as a GitHub Actions runner, deployed as a
[Raspberry Pi Connect script artefact](https://www.raspberrypi.com/documentation/services/connect.html#remoteupdate-intro).

Assumes the Pi is assembled, boards are on a powered USB hub, arm64 userland, and the boards
sit on the same VLAN as the Pi. Board detection and flashing use the repo's existing dev
pipeline (`dev/detect_boards.py`, `dev/sync.py`), so there is nothing bench-specific to
configure.

Everything lives in [`ota/`](ota/):

| File | Purpose |
|---|---|
| `vector-hil-runner-setup.tar.zst` | **the built artefact** — point Connect at this |
| `vector-hil-runner-setup.tar.zst.sha256` | its checksum, for the Connect UI |
| `hil-runner-setup.sh` | the script inside the artefact; runs as root on the Pi |
| `hil-runner-setup.yaml` | otamaker manifest |
| `vector-hil.conf.example` | template for the device-side config |
| `build.sh` | rebuilds the artefact and checksum reproducibly |

## Why the artefact is committed

The script carries **no credentials**. Secrets live in `/etc/vector-hil.conf` on the Pi, which
never enters the repo. That is what makes committing the artefact safe — and it also means
you never rebuild it to redeploy. Point Connect at the same URL every time.

The alternative — baking the token and WiFi password into the script before packaging — would
have published the bench WiFi password to a public repo the moment the artefact was committed.

## First deploy

**1. Put the config on the Pi.** Once per device, over Raspberry Pi Connect's shell or SSH:

```bash
sudo tee /etc/vector-hil.conf >/dev/null <<'EOF'
WIFI_SSID="your-bench-ssid"
WIFI_PASSWORD="your-bench-password"
REGISTRATION_TOKEN="paste-from-github"
EOF
sudo chmod 600 /etc/vector-hil.conf
sudo chown root:root /etc/vector-hil.conf
```

The registration token comes from repo → Settings → Actions → Runners → New self-hosted
runner. It is single-use and valid for one hour, so generate it just before deploying.

The script sources this file as root and refuses to run if it is group- or world-writable, or
not owned by root.

**2. Deploy** via Connect's remote update, pointing at the committed artefact:

```
https://raw.githubusercontent.com/warped-pinball/vector/main/dev/hil/ota/vector-hil-runner-setup.tar.zst
```

Paste the checksum from `vector-hil-runner-setup.tar.zst.sha256` when Connect asks. Connect
passes it to the device, which verifies the download before running anything.

> **Testing before this merges?** The `main` URL above doesn't exist until then. Use the
> branch instead — `raw.githubusercontent.com` serves any ref:
>
> ```
> https://raw.githubusercontent.com/warped-pinball/vector/claude/hil-testing-design-s564ln/dev/hil/ota/vector-hil-runner-setup.tar.zst
> ```
>
> Switch to the `main` URL after merging; branch URLs stop resolving once the branch is
> deleted. Note that GitHub's "Files changed" view doesn't render binary blobs, so the
> artefact won't appear as a readable diff in the PR even though it is committed — confirm it
> with `git cat-file blob <ref>:dev/hil/ota/vector-hil-runner-setup.tar.zst | sha256sum`.

Any HTTP, HTTPS, FTP, SFTP or `file://` URL the Pi can reach works — the location doesn't need
to be reachable by Connect's servers, only by the Pi.

**3. Watch it run:**

```bash
journalctl -t rpi-ota-connector -f
```

Expect roughly five minutes, most of it `pip install` building the dev pipeline.

**4. Blank the token** in `/etc/vector-hil.conf` once the runner is registered. It is spent,
and later redeploys don't need one.

## Redeploying

No rebuild, no new token, no config changes — just point Connect at the same URL again. This
is the normal way to refresh WiFi credentials (edit the conf first) or pull a newer harness.

The script is idempotent: an existing clone is fetched rather than re-cloned, an existing
runner download and registration are left alone, and `.env` is rewritten touching only the
`VECTOR_HIL_*` lines it owns, so anything else you set there survives.

To re-register against a different repo or token, remove the registration first — the script
deliberately won't do this behind your back:

```bash
cd ~/actions-runner && sudo ./svc.sh uninstall && ./config.sh remove --token <REMOVAL_TOKEN>
```

## Rebuilding the artefact

After changing `hil-runner-setup.sh` or the manifest:

```bash
cd dev/hil/ota && ./build.sh
```

Commit both the `.tar.zst` and the regenerated `.sha256`. The build is reproducible — fixed
mtimes, fixed ownership, sorted entries — so an unchanged source rebuilds byte-identically and
a changed checksum in a diff means the contents actually changed. `build.sh` also refuses to
package a script with literal credentials in it, and syntax-checks the script first.

> **Archive layout caveat.** The Connect docs say the artefact is a zstd-compressed tar
> "containing the manifest and the script" but don't document the internal layout, so this
> build puts both at the archive root. If the device rejects it, run `otamaker
> hil-runner-setup.yaml` once and compare `tar -tf` output against
> `zstd -dc vector-hil-runner-setup.tar.zst | tar -tv`, then adjust `build.sh` to match.

## What the script does

Runs as root, per the Connect artefact contract, and drops to `$RUNNER_USER` via `runuser` for
everything that shouldn't be root — the Actions runner refuses to be configured as root, and
shouldn't run as root regardless.

1. Reads and validates `/etc/vector-hil.conf`
2. Installs `git`, `python3-venv`, `curl`; adds the runner user to `dialout` for serial access
3. Clones (or fetches) the repo and builds a venv from `dev/requirements.txt`
4. Runs `dev/detect_boards.py` and logs what it found
5. Downloads the Actions runner, registers it with the `vector-hil` label
6. Writes bench credentials to the runner's `.env`
7. Installs and starts the systemd service, then verifies the unit is actually active

Exit codes follow the Connect contract: `0` success, `1` failure, `2` success-plus-reboot. The
script never returns `2` — nothing it does needs a reboot, because systemd reads the new
`dialout` membership when it starts the service.

**Board detection is non-fatal.** A board that is unplugged or mid-reset logs a warning and the
deployment continues, rather than failing the whole setup over a transient USB state. Bench
health is the pre-job check's job, not the installer's.

## Verify

The runner should show **Idle** under Settings → Actions → Runners with the `vector-hil` label.
Confirm end to end with a workflow on a branch:

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

- **Where did it fail?** `journalctl -t rpi-ota-connector` — every phase logs a line, and each
  failure exits with a specific message.
- **`/etc/vector-hil.conf not found`** — step 1 hasn't been done on this Pi.
- **`runner registration failed`** — almost always an expired token. They last one hour. Put a
  fresh one in the conf and redeploy; no rebuild needed.
- **Jobs get OOM-killed** (`dmesg -T | grep -i oom`) — 512 MB is tight on a Zero 2 W.
  `sudo apt install -y zram-tools` gets you compressed swap with no further config.
- **Runner won't start, globalization error** — libicu missing. Re-run
  `~/actions-runner/bin/installdependencies.sh`, or add
  `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` to `~/actions-runner/.env`.
- **`.env` changes have no effect** — it is read at service start.
  `cd ~/actions-runner && sudo ./svc.sh stop && sudo ./svc.sh start`.
- **You need to tell two boards of the same type apart** — `detect_boards.py` identifies boards
  by querying `systemConfig.vectorSystem`, so port order doesn't matter for distinct board
  types. Only add udev rules if you have two of the same type.

See [DESIGN.md](DESIGN.md) for the test architecture and the security model for fork PRs.
