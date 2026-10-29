#!/usr/bin/env python3
"""Check the security fixes from the WarpedPinball-1 report on real boards.

Run after flash_and_check.py, against the firmware it just flashed:

    cd ~/vector && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python dev/hil/security_checks.py

Everything here goes over HTTP, because USB requests skip authentication by
design (backend.py require_auth) and so cannot prove a gate works. Each board
is checked in turn:

  F-08  /api/player/scores refuses an out of range player id
  F-01  /api/scores/claim refuses a score that is not in the claim list and a
        score that is not a number, and the leaderboard does not change
  F-03  /api/time/trigger_midnight_madness refuses an unsigned request and
        accepts a signed one (or refuses it with a 400 on a machine without the clock)
  auth  a correctly signed request is accepted
  F-08  a signed /api/player/scores/reset refuses an out of range player id
  F-02  five bad signatures lock every signed route for 30 seconds
  F-05  /api/update/check returns only a verified release record
  F-04  /api/update/apply refuses a package with no checksum, a wrong
        checksum, a bad signature or a corrupted body, the board keeps its
        version, and the refused download is deleted from flash
  logs  no scheduled task failed while all of that ran (the WPC machine high
        score regression showed up only as a scheduled task error)

The update packages are made up here and served from this machine, so the
check depends neither on the live update site nor on a signing key. None of
them is ever installed: every one is meant to be refused before a file is
written.

F-07 (AP setup) is not covered: the bench cannot put a board in AP mode
(DESIGN.md, non-goals).
"""

import argparse
import hashlib
import hmac
import http.server
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trench_coat  # noqa: E402
from bench import (  # noqa: E402
    BootCrash,
    CheckFailure,
    UsbApiClient,
    _ask_board,
    _dump_boot_log,
    endgroup,
    ensure_tools_on_path,
    get,
    group,
    inventory,
    log,
    parse_board_map,
    prime_usb,
    reset_board,
    reset_board_with_drain,
    resolve_targets,
    wait_for_server,
)

# Must match what flash_and_check.py wrote to the boards (bench.write_bench_config).
DEFAULT_GAME_PASSWORD = "hiltest"

# backend.py: _AUTH_MAX_FAILURES and _AUTH_LOCKOUT_SECONDS.
AUTH_MAX_FAILURES = 5
AUTH_LOCKOUT_SECONDS = 30

# An apply that fails fast still waits on the board looking up the latest
# release over the internet when it is given no checksum, which can take the
# board's whole 10 s request timeout on a bench with no egress.
APPLY_TIMEOUT = 120
HTTP_TIMEOUT = 15

# Lines the board prints when a scheduled task raises. The claim list one is
# what the WPC regression in #436 looked like, every 5 seconds.
TASK_ERROR = "Error running scheduled task"


class SerialTap:
    """Keep reading the board's console while the HTTP checks run.

    Two reasons. The board's prints go out over the same USB endpoint, and a
    board writing into an endpoint nobody drains can stall. And the console is
    the only place a scheduled task's failure shows up at all.
    """

    def __init__(self, connection):
        self.connection = connection
        self.lines = []
        self._partial = b""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_exc):
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self):
        while not self._stop.is_set():
            try:
                chunk = self.connection.read(self.connection.in_waiting or 1)
            except Exception:
                return
            if not chunk:
                continue
            self._partial += chunk
            *complete, self._partial = self._partial.split(b"\n")
            self.lines.extend(line.decode(errors="replace").rstrip("\r") for line in complete)

    def task_errors(self):
        return [line for line in self.lines if TASK_ERROR in line]


def sign(password, challenge, path, body=""):
    """The HMAC the web UI sends (utils.js smartFetch, backend.py require_auth)."""
    message = (challenge + path + body).encode("utf-8")
    return hmac.new(password.encode("utf-8"), message, hashlib.sha256).hexdigest()


def compact(data):
    # JSON.stringify's spacing, which is what the HMAC is computed over.
    return json.dumps(data, separators=(",", ":"))


class Board:
    """HTTP access to one board, signed or not."""

    def __init__(self, ip, password):
        self.base = f"http://{ip}"
        self.password = password

    def request(self, path, data=None, headers=None, timeout=HTTP_TIMEOUT):
        """Return (status, body text). An HTTP error status is an answer, not an exception."""
        body = compact(data) if data is not None else None
        request = urllib.request.Request(
            self.base + path,
            data=body.encode("utf-8") if body is not None else None,
            method="POST" if body is not None else "GET",
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read().decode(errors="replace")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode(errors="replace")

    def challenge(self):
        status, body = self.request("/api/auth/challenge")
        if status != 200:
            raise CheckFailure(f"/api/auth/challenge returned {status}")
        return json.loads(body)["challenge"]

    def signed(self, path, data=None, password=None, timeout=HTTP_TIMEOUT):
        challenge = self.challenge()
        body = compact(data) if data is not None else ""
        headers = {
            "X-Auth-HMAC": sign(password if password is not None else self.password, challenge, path, body),
            "X-Auth-Challenge": challenge,
        }
        return self.request(path, data, headers=headers, timeout=timeout)


def expect(what, status, body, allowed):
    allowed = (allowed,) if isinstance(allowed, int) else tuple(allowed)
    if status not in allowed:
        raise CheckFailure(f"{what}: got {status}, expected {' or '.join(map(str, allowed))}. Body: {body[:200]!r}")
    log(f"    ok  {what}: {status}")


def check_player_bounds(board):
    for player_id in (9999, -1):
        status, body = board.request("/api/player/scores", {"id": player_id})
        expect(f"F-08 player scores for id {player_id}", status, body, 400)
    status, body = board.request("/api/player/scores", {"id": 0})
    expect("F-08 player scores for id 0 still answer", status, body, 200)


def check_claims(board):
    before = board.request("/api/leaders")
    # 403 is the same refusal on a board where score claiming is switched off.
    status, body = board.request("/api/scores/claim", {"initials": "HIL", "player_index": 0, "score": 1234567})
    expect("F-01 claim for a score that is not in the claim list", status, body, (400, 403))
    bad_claims = [
        ("a score that is not a number", {"initials": "HIL", "player_index": 0, "score": "1234567"}),
        ("a bool score", {"initials": "HIL", "player_index": 0, "score": True}),
        ("a negative score", {"initials": "HIL", "player_index": 0, "score": -5}),
        ("initials that are not a string", {"initials": 123, "player_index": 0, "score": 1234567}),
        ("player_index 9", {"initials": "HIL", "player_index": 9, "score": 1234567}),
    ]
    for name, data in bad_claims:
        status, body = board.request("/api/scores/claim", data)
        expect(f"F-01 claim with {name}", status, body, (400, 403))
    if board.request("/api/leaders") != before:
        raise CheckFailure("F-01 the leaderboard changed after two refused claims")
    log("    ok  F-01 leaderboard unchanged")


def check_auth(board):
    status, body = board.request("/api/time/trigger_midnight_madness")
    expect("F-03 unsigned trigger_midnight_madness", status, body, 401)

    # Also clears the failure count the unsigned request just added to.
    status, body = board.signed("/api/auth/password_check")
    expect("signed password_check", status, body, 200)

    # Bare boards on the bench, so firing it has nothing to act on. Only a
    # machine with the clock can run it; the rest refuse it after auth passes.
    status, body = board.request("/api/time/midnight_madness_available")
    expect("midnight_madness_available", status, body, 200)
    available = json.loads(body).get("available")
    status, body = board.signed("/api/time/trigger_midnight_madness")
    expect("F-03 signed trigger_midnight_madness", status, body, 200 if available else 400)

    for player_id in (9999, -1):
        status, body = board.signed("/api/player/scores/reset", {"id": player_id})
        expect(f"F-08 signed score reset for id {player_id}", status, body, 400)


def check_lockout(board):
    for attempt in range(1, AUTH_MAX_FAILURES + 1):
        status, body = board.signed("/api/auth/password_check", password="not-the-password")
        expect(f"F-02 bad signature {attempt} of {AUTH_MAX_FAILURES}", status, body, 401)

    # The lock is global, so even a correct signature is turned away.
    status, body = board.signed("/api/auth/password_check")
    expect("F-02 correct signature during the lockout", status, body, 429)

    log(f"    waiting {AUTH_LOCKOUT_SECONDS + 2}s for the lockout to expire")
    time.sleep(AUTH_LOCKOUT_SECONDS + 2)
    status, body = board.signed("/api/auth/password_check")
    expect("F-02 correct signature after the lockout", status, body, 200)


def check_update_check(board):
    status, body = board.request("/api/update/check", timeout=30)
    if status == 200:
        record = json.loads(body)
        missing = [key for key in ("version", "url", "sha256") if not record.get(key)]
        if missing or "signed" in record:
            raise CheckFailure(f"F-05 /api/update/check returned something other than a verified release record: {body[:200]!r}")
        log(f"    ok  F-05 update check: verified record for {record['version']}")
    elif status == 502 and "Could not verify" in body:
        # The bench has no route to the update site, or the site is unsigned.
        log(f"    ok  F-05 update check: 502, {json.loads(body).get('error')}")
    else:
        raise CheckFailure(f"F-05 /api/update/check returned {status}: {body[:200]!r}")


def update_package(corrupt=False):
    """A minimal update file: content, then {"sha256","signature"} on the last line.

    The embedded sha256 is right, so the board gets past its own hash check
    and the refusal comes from the gate under test. The signature is junk:
    nothing here holds the signing key, and nothing should need it.
    """
    content = b'{"version":"hil-refuse-me"}\nhil-security-check.txt{"execute":false}aGls\n'
    digest = hashlib.sha256(content.rstrip(b"\n")).hexdigest()
    if corrupt:
        content = content.replace(b"hil-refuse-me", b"hil-refuse-mf")
    signature = "aGlsLXRoaXMtaXMtbm90LWEtc2lnbmF0dXJl"
    return content + json.dumps({"sha256": digest, "signature": signature}).encode() + b"\n", digest


class PackageServer:
    """Serve update packages to the boards from this machine for the duration of the check."""

    def __init__(self, port=0):
        self.packages = {}
        self.requests = []
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                server.requests.append(self.path)
                body = server.packages.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url_for(self, board_ip, path):
        # The address this machine uses to reach the board is the one the board can reach back.
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect((board_ip, 80))
            host = probe.getsockname()[0]
        finally:
            probe.close()
        return f"http://{host}:{self.port}{path}"

    def close(self):
        self.httpd.shutdown()


def check_update_refusals(board, ip, server, version):
    good, digest = update_package()
    corrupt, _ = update_package(corrupt=True)
    server.packages = {"/refuse.json": good, "/corrupt.json": corrupt}
    url = server.url_for(ip, "/refuse.json")

    cases = [
        ("no checksum", {"url": url}),
        ("wrong checksum (developer build)", {"url": url, "skip_signature_check": True, "sha256": "0" * 64}),
        ("bad signature", {"url": url, "sha256": digest}),
        ("corrupted body (developer build)", {"url": server.url_for(ip, "/corrupt.json"), "skip_signature_check": True}),
    ]
    for name, data in cases:
        served = len(server.requests)
        status, body = board.signed("/api/update/apply", data, timeout=APPLY_TIMEOUT)
        if status != 200:
            raise CheckFailure(f"F-04 apply with {name}: got {status}: {body[:200]!r}")
        if len(server.requests) == served:
            raise CheckFailure(f"F-04 apply with {name}: the board never downloaded the package from {data['url']}, so nothing was tested. Can the board reach this machine?")
        if "Writing files to board" in body or "Update complete" in body:
            raise CheckFailure(f"F-04 apply with {name} was not refused: {body[-300:]!r}")
        if "Error applying update" not in body:
            raise CheckFailure(f"F-04 apply with {name} did not report a refusal: {body[-300:]!r}")
        reason = body.split("Error applying update:", 1)[1].split('"', 1)[0].strip()
        log(f"    ok  F-04 apply with {name}: refused ({reason})")

        status, body = board.request("/api/version")
        if status != 200 or str(json.loads(body).get("version")) != str(version):
            raise CheckFailure(f"F-04 the board's version changed after a refused update: {status} {body[:120]!r}")
    log(f"    ok  F-04 board still on {version} after {len(cases)} refused updates")


def check_board(b, password, server):
    port = b["port"]
    reset_board_with_drain(port)
    for attempt in range(2):
        try:
            connection, boot_log = wait_for_server(port)
            break
        except BootCrash as crash:
            if attempt:
                raise
            log(f"::warning::{port} crashed on boot; retrying once. {crash}")
            reset_board(port)
    b["boot_log"] = boot_log
    prime_usb(connection)
    client = UsbApiClient(connection)
    try:
        version = get(client, "/api/version").get("version")
        last_ip = get(client, "/api/last_ip")
        ip = last_ip.get("ip") if isinstance(last_ip, dict) else None
        if not ip:
            raise CheckFailure("board reported no IP address - it did not join the bench wifi")
        b["ip"] = ip
        board = Board(ip, password)

        with SerialTap(connection) as tap:
            check_player_bounds(board)
            check_claims(board)
            check_auth(board)
            check_update_check(board)
            check_update_refusals(board, ip, server, version)
            # Last, so its 30 s lock cannot turn any check above into a 429.
            check_lockout(board)
            # Leave the score task a few runs (every 5 s) to show an error.
            time.sleep(12)

        errors = tap.task_errors()
        if errors:
            raise CheckFailure("a scheduled task failed during the checks:\n      " + "\n      ".join(errors[:5]))
        log("    ok  no scheduled task errors")
    finally:
        try:
            client.close()
        except Exception:
            pass

    leftover = _ask_board(port, "import os; print('update.json' in os.listdir())")
    if leftover is None or leftover.returncode != 0:
        raise CheckFailure(f"could not list the board's files to look for update.json: {leftover and (leftover.stderr or leftover.stdout)}")
    if leftover.stdout.strip() != "False":
        raise CheckFailure("F-04 a refused update left update.json on flash")
    log("    ok  F-04 no update.json left on flash")
    # mpremote left the board at the REPL; put it back to running the app.
    reset_board(port)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", action="append", help="only check boards for this target (repeatable), e.g. --target wpc")
    parser.add_argument("--package-port", type=int, default=int(os.environ.get("VECTOR_HIL_PACKAGE_PORT", "0")), help="port to serve the update packages on (default: any free port)")
    args = parser.parse_args()

    ensure_tools_on_path()
    password = os.environ.get("VECTOR_HIL_GAME_PASSWORD", DEFAULT_GAME_PASSWORD)
    board_map = parse_board_map(os.environ.get("VECTOR_HIL_BOARD_MAP"))
    trench_coat.rescue_bootsel(board_map, Path(__file__).resolve().parents[2] / "build" / "hil")

    group("Inventory")
    boards = [b for b in inventory(board_map) if b.get("responsive", True)]
    boards = resolve_targets(boards, board_map)
    if args.target:
        boards = [b for b in boards if b["target"] in set(args.target)]
    endgroup()
    if not boards:
        raise CheckFailure("no board on the bench is answering")

    server = PackageServer(args.package_port)
    failures = []
    try:
        for b in boards:
            group(f"Security checks {b['target']} on {b['port']}")
            try:
                check_board(b, password, server)
            except CheckFailure as exc:
                log(f"::error::{exc}")
                _dump_boot_log(b)
                failures.append(f"{b['port']} ({b['target']}): {exc}")
            except Exception as exc:
                log(f"::error::unexpected error: {exc}")
                _dump_boot_log(b)
                failures.append(f"{b['port']} ({b['target']}): {exc}")
            finally:
                endgroup()
    finally:
        server.close()

    log("")
    log("=" * 60)
    for b in boards:
        state = "FAIL" if any(b["port"] in f for f in failures) else "ok"
        log(f"  {state:5} {b['port']:16} {b['target']:12} {b.get('ip') or ''}")
    log("=" * 60)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as handle:
            handle.write("### Security checks\n\n| board | target | result |\n|---|---|---|\n")
            for b in boards:
                state = "FAIL" if any(b["port"] in f for f in failures) else "ok"
                handle.write(f"| `{b['port']}` | {b['target']} | {state} |\n")
            handle.write("".join(f"\n- {f}" for f in failures) + "\n")

    if failures:
        log(f"\n{len(failures)} failure(s):")
        for failure in failures:
            log(f"  - {failure}")
        return 1
    log(f"\nall {len(boards)} board(s) passed the security checks")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckFailure as exc:
        log(f"::error::{exc}")
        sys.exit(1)
