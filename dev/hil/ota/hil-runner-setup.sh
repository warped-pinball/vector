#!/bin/sh
#
# Vector HIL bench — GitHub Actions runner setup.
#
# Deployed as a Raspberry Pi Connect script artefact. Runs as root on the
# target Pi; everything that should not be root is run via runuser.
#
# Exit codes are the Connect contract:
#   0  success
#   1  failure
#   2  success, device needs a reboot
#
# Output goes to the device journal: journalctl -t rpi-ota-connector
#
# Safe to re-run. If the runner is already registered it is left alone and
# only the environment file and service state are refreshed.

set -eu

# --------------------------------------------------------------------------
# Configuration — fill these in before running otamaker.
#
# REGISTRATION_TOKEN comes from the repo's
#   Settings -> Actions -> Runners -> New self-hosted runner
# and is single-use and valid for one hour, so build and deploy promptly.
# --------------------------------------------------------------------------
RUNNER_USER="pi"
REPO_URL="https://github.com/warped-pinball/vector"
REGISTRATION_TOKEN="PASTE_REGISTRATION_TOKEN"
RUNNER_LABELS="vector-hil"
RUNNER_VERSION="2.336.0"
RUNNER_ARCH="arm64"
WIFI_SSID="PASTE_BENCH_SSID"
WIFI_PASSWORD="PASTE_BENCH_PASSWORD"
# --------------------------------------------------------------------------

EXIT_FAILURE=1

log() { echo "[hil-setup] $*"; }
fail() { echo "[hil-setup] ERROR: $*" >&2; exit "$EXIT_FAILURE"; }

as_user() { runuser -u "$RUNNER_USER" -- "$@"; }

# --- preflight ------------------------------------------------------------

[ "$(id -u)" -eq 0 ] || fail "must run as root"

for placeholder in "$REGISTRATION_TOKEN" "$WIFI_SSID" "$WIFI_PASSWORD"; do
    case "$placeholder" in
        PASTE_*) fail "configuration placeholders not filled in before packaging" ;;
    esac
done

id "$RUNNER_USER" >/dev/null 2>&1 || fail "user '$RUNNER_USER' does not exist"

USER_HOME=$(getent passwd "$RUNNER_USER" | cut -d: -f6)
[ -n "$USER_HOME" ] && [ -d "$USER_HOME" ] || fail "no home directory for '$RUNNER_USER'"

REPO_DIR="$USER_HOME/vector"
RUNNER_DIR="$USER_HOME/actions-runner"
VENV_DIR="$REPO_DIR/.venv"

log "installing for user '$RUNNER_USER' (home: $USER_HOME)"

# --- system packages ------------------------------------------------------

log "installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update >/dev/null 2>&1 || fail "apt-get update failed"
apt-get install -y git python3-venv curl >/dev/null 2>&1 \
    || fail "apt-get install failed"

# Serial access to the Picos. Group membership is read by systemd when the
# runner service starts, and we start it below, so no reboot is needed.
if ! id -nG "$RUNNER_USER" | grep -qw dialout; then
    log "adding $RUNNER_USER to dialout"
    usermod -aG dialout "$RUNNER_USER"
fi

# --- repo and dev pipeline ------------------------------------------------

if [ -d "$REPO_DIR/.git" ]; then
    log "updating existing clone at $REPO_DIR"
    as_user git -C "$REPO_DIR" fetch --quiet origin \
        || log "WARNING: git fetch failed, continuing with the existing checkout"
else
    log "cloning $REPO_URL"
    as_user git clone --quiet "$REPO_URL" "$REPO_DIR" || fail "git clone failed"
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    log "creating virtualenv"
    as_user python3 -m venv "$VENV_DIR" || fail "venv creation failed"
fi

log "installing dev pipeline requirements (this takes a few minutes)"
as_user "$VENV_DIR/bin/pip" install --quiet --upgrade pip \
    || fail "pip self-upgrade failed"
as_user "$VENV_DIR/bin/pip" install --quiet -r "$REPO_DIR/dev/requirements.txt" \
    || fail "pip install of dev/requirements.txt failed"

# --- board check ----------------------------------------------------------
# Non-fatal: a board that is unplugged or mid-reset should not fail the whole
# deployment. It is logged loudly and the pre-job bench check owns it later.

log "detecting boards"
if boards=$(as_user "$VENV_DIR/bin/python" "$REPO_DIR/dev/detect_boards.py" 2>&1); then
    log "detected: $boards"
    case "$boards" in
        '{}'|'') log "WARNING: no boards detected - check the USB hub and power" ;;
    esac
else
    log "WARNING: board detection failed: $boards"
fi

# --- actions runner -------------------------------------------------------

TARBALL="actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"
RUNNER_TARBALL_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}"

as_user mkdir -p "$RUNNER_DIR"

if [ ! -x "$RUNNER_DIR/config.sh" ]; then
    log "downloading actions runner $RUNNER_VERSION ($RUNNER_ARCH)"
    as_user curl -fSL --retry 3 -o "$RUNNER_DIR/$TARBALL" "$RUNNER_TARBALL_URL" \
        || fail "runner download failed"
    as_user tar -xzf "$RUNNER_DIR/$TARBALL" -C "$RUNNER_DIR" \
        || fail "runner extraction failed"
    as_user rm -f "$RUNNER_DIR/$TARBALL"

    log "installing runner dependencies"
    "$RUNNER_DIR/bin/installdependencies.sh" >/dev/null 2>&1 \
        || fail "installdependencies.sh failed"
else
    log "runner already present, skipping download"
fi

# config.sh refuses to run as root and errors if already configured, so
# re-registration is a deliberate manual step rather than something this
# script does behind your back.
if [ -f "$RUNNER_DIR/.runner" ]; then
    log "runner already registered, leaving registration untouched"
else
    log "registering runner with $REPO_URL"
    as_user sh -c "cd '$RUNNER_DIR' && ./config.sh \
        --url '$REPO_URL' \
        --token '$REGISTRATION_TOKEN' \
        --labels '$RUNNER_LABELS' \
        --unattended --replace" >/dev/null 2>&1 \
        || fail "runner registration failed - the token may have expired (they last one hour)"
fi

# --- bench environment ----------------------------------------------------
# The runner reads .env at service start and exports it into every job.
# Rewrite only the lines this script owns so anything else set there survives.

ENV_FILE="$RUNNER_DIR/.env"
log "writing bench environment to $ENV_FILE"

TMP_ENV="${ENV_FILE}.new"
: > "$TMP_ENV"
if [ -f "$ENV_FILE" ]; then
    grep -v '^VECTOR_HIL_' "$ENV_FILE" >> "$TMP_ENV" || true
fi
{
    echo "VECTOR_HIL_WIFI_SSID=$WIFI_SSID"
    echo "VECTOR_HIL_WIFI_PASSWORD=$WIFI_PASSWORD"
    echo "VECTOR_HIL_VENV=$VENV_DIR"
    echo "VECTOR_HIL_REPO=$REPO_DIR"
} >> "$TMP_ENV"
mv "$TMP_ENV" "$ENV_FILE"
chown "$RUNNER_USER": "$ENV_FILE"
chmod 600 "$ENV_FILE"

# --- service --------------------------------------------------------------

cd "$RUNNER_DIR"

if [ -f "$RUNNER_DIR/.service" ]; then
    log "restarting existing runner service"
    ./svc.sh stop >/dev/null 2>&1 || true
else
    log "installing runner service"
    ./svc.sh install "$RUNNER_USER" >/dev/null 2>&1 || fail "svc.sh install failed"
fi

./svc.sh start >/dev/null 2>&1 || fail "svc.sh start failed"

# Give systemd a moment, then confirm the unit actually came up rather than
# reporting success for a service that immediately died.
sleep 5
SERVICE_NAME=$(cat "$RUNNER_DIR/.service" 2>/dev/null || echo "")
if [ -n "$SERVICE_NAME" ] && ! systemctl is-active --quiet "$SERVICE_NAME"; then
    log "service status:"
    systemctl status "$SERVICE_NAME" --no-pager --lines=20 || true
    fail "runner service is not active after start"
fi

log "runner service '$SERVICE_NAME' is active"
log "setup complete - the runner should show Idle with label '$RUNNER_LABELS'"

exit 0
