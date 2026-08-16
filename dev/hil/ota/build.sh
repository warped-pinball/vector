#!/bin/sh
#
# Build the Raspberry Pi Connect update artefact and write its checksum.
#
#   ./build.sh
#
# Produces, in this directory:
#   vector-hil-runner-setup.tar.zst          the artefact
#   vector-hil-runner-setup.tar.zst.sha256   its SHA-256, for the Connect UI
#
# The archive is built reproducibly - fixed mtimes, fixed ownership, sorted
# entries - so rebuilding from an unchanged source produces a byte-identical
# file and the committed checksum stays meaningful in diffs.
#
# The artefact contains no credentials; those live in /etc/vector-hil.conf on
# the device. That is what makes it safe to commit and redeploy unchanged.

set -eu

cd "$(dirname "$0")"

ARTEFACT="vector-hil-runner-setup.tar.zst"
MANIFEST="hil-runner-setup.yaml"
SCRIPT="hil-runner-setup.sh"

for f in "$MANIFEST" "$SCRIPT"; do
    [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
done

# Refuse to package a script someone has pasted credentials into.
if grep -qE '^(WIFI_PASSWORD|REGISTRATION_TOKEN)="..*"' "$SCRIPT"; then
    echo "ERROR: $SCRIPT appears to contain literal credentials." >&2
    echo "Secrets belong in /etc/vector-hil.conf on the device, not the artefact." >&2
    exit 1
fi

sh -n "$SCRIPT" || { echo "ERROR: $SCRIPT is not valid POSIX sh" >&2; exit 1; }

tar --create \
    --file - \
    --sort=name \
    --owner=root:0 \
    --group=root:0 \
    --numeric-owner \
    --mtime='UTC 2020-01-01' \
    --mode='u=rwX,go=rX' \
    --format=gnu \
    "$MANIFEST" "$SCRIPT" \
  | zstd --quiet --force -19 -o "$ARTEFACT"

sha256sum "$ARTEFACT" > "${ARTEFACT}.sha256"

echo "built $ARTEFACT"
echo "  size:   $(wc -c < "$ARTEFACT") bytes"
echo "  sha256: $(cut -d' ' -f1 < "${ARTEFACT}.sha256")"
echo
echo "contents:"
zstd --decompress --stdout "$ARTEFACT" | tar --list --verbose
