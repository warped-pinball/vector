#!/bin/sh
#
# Vector HIL bench — GitHub Actions runner setup.
#
# Run on the bench Pi as your normal login user (not root — the Actions
# runner refuses to be configured as root). Uses sudo for the parts that
# need it.
#
#   export VECTOR_HIL_WIFI_SSID="bench-ssid"
#   export VECTOR_HIL_WIFI_PASSWORD="bench-password"
#   export RUNNER_TOKEN="from github, see below"
#   ./setup-runner.sh
#
# RUNNER_TOKEN comes from the repo's
#   Settings -> Actions -> Runners -> New self-hosted runner
# It is single-use and valid for one hour. It is only needed the first
# time; once the runner is registered you can re-run this without it.
#
# Safe to re-run: an existing clone is fetched rather than re-cloned, an
# existing runner download and registration are left alone, and only the
# VECTOR_HIL_* lines in the runner's .env are rewritten.

set -eu

REPO_URL="${REPO_URL:-https://github.com/warped-pinball/vector}"
RUNNER_LABELS="${RUNNER_LABELS:-vector-hil}"
RUNNER_VERSION="${RUNNER_VERSION:-2.336.0}"
RUNNER_ARCH="${RUNNER_ARCH:-arm64}"

REPO_DIR="$HOME/vector"
RUNNER_DIR="$HOME/actions-runner"
VENV_DIR="$REPO_DIR/.venv"

log() { echo "==> $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

# --- preflight ------------------------------------------------------------

[ "$(id -u)" -ne 0 ] || fail "run as your normal user, not root (the runner will not configure as root)"

[ -n "${VECTOR_HIL_WIFI_SSID:-}" ] || fail "VECTOR_HIL_WIFI_SSID is not set"
[ -n "${VECTOR_HIL_WIFI_PASSWORD:-}" ] || fail "VECTOR_HIL_WIFI_PASSWORD is not set"

if [ ! -f "$RUNNER_DIR/.runner" ] && [ -z "${RUNNER_TOKEN:-}" ]; then
    fail "RUNNER_TOKEN is not set and the runner is not registered yet"
fi

# Prompt for sudo once here rather than halfway through.
sudo -v || fail "sudo is required"

# --- system packages ------------------------------------------------------

log "installing system packages"
sudo apt-get update -qq || fail "apt-get update failed"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git python3-venv curl \
    || fail "apt-get install failed"

# Serial access to the Picos. systemd reads group membership when it starts
# the runner service below, so no reboot is needed.
if ! id -nG | grep -qw dialout; then
    log "adding $(whoami) to dialout"
    sudo usermod -aG dialout "$(whoami)"
fi

# --- repo and dev pipeline ------------------------------------------------

if [ -d "$REPO_DIR/.git" ]; then
    log "updating existing clone at $REPO_DIR"
    git -C "$REPO_DIR" fetch --quiet origin || echo "WARNING: git fetch failed, using existing checkout"
else
    log "cloning $REPO_URL"
    git clone --quiet "$REPO_URL" "$REPO_DIR" || fail "git clone failed"
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    log "creating virtualenv"
    python3 -m venv "$VENV_DIR" || fail "venv creation failed"
fi

log "installing dev pipeline requirements (a few minutes)"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip || fail "pip self-upgrade failed"
"$VENV_DIR/bin/pip" install --quiet -r "$REPO_DIR/dev/requirements.txt" \
    || fail "pip install of dev/requirements.txt failed"

# --- board check ----------------------------------------------------------
# Non-fatal: a board unplugged or mid-reset should not abort the setup.

log "detecting boards"
if boards=$("$VENV_DIR/bin/python" "$REPO_DIR/dev/detect_boards.py" 2>&1); then
    echo "    $boards"
    case "$boards" in
        '{}'|'') echo "    WARNING: no boards detected - check the USB hub and power" ;;
    esac
else
    echo "    WARNING: board detection failed: $boards"
fi

# --- actions runner -------------------------------------------------------

TARBALL="actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"

mkdir -p "$RUNNER_DIR"

if [ ! -x "$RUNNER_DIR/config.sh" ]; then
    log "downloading actions runner $RUNNER_VERSION ($RUNNER_ARCH)"
    curl -fSL --retry 3 -o "$RUNNER_DIR/$TARBALL" \
        "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}" \
        || fail "runner download failed"
    tar -xzf "$RUNNER_DIR/$TARBALL" -C "$RUNNER_DIR" || fail "runner extraction failed"
    rm -f "$RUNNER_DIR/$TARBALL"

    log "installing runner dependencies"
    sudo "$RUNNER_DIR/bin/installdependencies.sh" >/dev/null \
        || fail "installdependencies.sh failed"
else
    log "runner already downloaded, skipping"
fi

if [ -f "$RUNNER_DIR/.runner" ]; then
    log "runner already registered, leaving registration alone"
else
    log "registering runner"
    ( cd "$RUNNER_DIR" && ./config.sh \
        --url "$REPO_URL" \
        --token "$RUNNER_TOKEN" \
        --labels "$RUNNER_LABELS" \
        --unattended --replace >/dev/null ) \
        || fail "registration failed - the token may have expired (they last one hour)"
fi

# --- bench environment ----------------------------------------------------
# The runner reads .env at service start and exports it into every job.
# Only rewrite the lines we own so anything else set there survives.

ENV_FILE="$RUNNER_DIR/.env"
log "writing bench environment"

TMP_ENV="${ENV_FILE}.new"
: > "$TMP_ENV"
[ -f "$ENV_FILE" ] && { grep -v '^VECTOR_HIL_' "$ENV_FILE" >> "$TMP_ENV" || true; }
{
    echo "VECTOR_HIL_WIFI_SSID=$VECTOR_HIL_WIFI_SSID"
    echo "VECTOR_HIL_WIFI_PASSWORD=$VECTOR_HIL_WIFI_PASSWORD"
    echo "VECTOR_HIL_VENV=$VENV_DIR"
    echo "VECTOR_HIL_REPO=$REPO_DIR"
} >> "$TMP_ENV"
mv "$TMP_ENV" "$ENV_FILE"
chmod 600 "$ENV_FILE"

# --- service --------------------------------------------------------------

cd "$RUNNER_DIR"

if [ -f "$RUNNER_DIR/.service" ]; then
    log "restarting runner service"
    sudo ./svc.sh stop >/dev/null 2>&1 || true
else
    log "installing runner service"
    sudo ./svc.sh install "$(whoami)" >/dev/null || fail "svc.sh install failed"
fi

sudo ./svc.sh start >/dev/null || fail "svc.sh start failed"

# Confirm the unit actually stayed up rather than reporting success for a
# service that immediately died.
sleep 5
SERVICE_NAME=$(cat "$RUNNER_DIR/.service" 2>/dev/null || echo "")
if [ -n "$SERVICE_NAME" ] && ! systemctl is-active --quiet "$SERVICE_NAME"; then
    systemctl status "$SERVICE_NAME" --no-pager --lines=20 || true
    fail "runner service is not active after start"
fi

log "done - runner '$SERVICE_NAME' is active with label '$RUNNER_LABELS'"
