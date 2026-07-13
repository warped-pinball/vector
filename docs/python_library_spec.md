# Warped Pinball Vector — Python Client Library Specification

This document is an implementation specification for a Python library (`warped-pinball-vector`, importable as `warpedpinball`) that wraps the Vector HTTP + USB APIs. It is written to be handed to an implementer with no prior knowledge of the Vector firmware. All protocol facts below were verified against the firmware source in this repository (`src/common/backend.py`, `src/common/discovery.py`, `src/common/usb_comms.py`, `src/common/phew/server.py`) and the generated docs (`docs/routes.md`, `docs/authentication.md`, `docs/discovery.md`, `docs/usb.md`).

## 1. Background: what a Vector is

Vector is a WiFi board (Raspberry Pi Pico 2W running MicroPython) installed inside a pinball machine. It exposes:

- An **HTTP API** on port 80 (plain HTTP, no TLS) — the full route list is in `docs/routes.md`.
- A **UDP peer-discovery protocol** on port `37020` so boards (and clients) on a LAN can find each other.
- A **USB serial transport** that tunnels the *same* HTTP routes over a pipe-delimited line protocol at 115200 baud.
- **HMAC-SHA256 challenge/response authentication** for mutating routes, keyed on a per-device password.

Constraints to design around: the device is a microcontroller. It is single-threaded, slow (hundreds of ms per request), memory constrained, and some routes have server-side cooldowns (`/api/logs` 10s, `/api/update/check` 10s, `/api/adjustments/restore` 5s) or single-instance locks (all authenticated routes are single-instance). The client library must be gentle: serialize requests per machine, use timeouts, and surface HTTP 409 ("Already running") and 429 responses as typed errors with retry guidance.

## 2. Package layout

```
warpedpinball/
    __init__.py          # re-exports: connect, discover, Machine, exceptions
    discovery.py         # UDP discovery client
    machine.py           # Machine class (transport-agnostic)
    transports/
        __init__.py      # Transport ABC
        http.py          # HTTP transport (requests or httpx)
        usb.py           # USB serial transport (pyserial)
    auth.py              # challenge fetch + HMAC signing
    addresses.py         # AddressMap (named memory addresses)
    exceptions.py
    cli.py               # optional `vector` console entry point
```

Distribution name `warped-pinball-vector` on PyPI. Support Python 3.9+. Runtime deps: `requests` (or `httpx`) and `pyserial` (make pyserial an optional extra: `pip install warped-pinball-vector[usb]`).

Top-level ergonomics (the exact names requested by the product owner):

```python
import warpedpinball

machines = warpedpinball.discover(timeout=5)     # -> list[DiscoveredMachine]
m = warpedpinball.connect("elvira")              # find by name on the LAN and return a Machine
m = warpedpinball.connect("192.168.1.42")        # or by IP, skipping discovery
m = warpedpinball.connect_usb("/dev/ttyACM0")    # USB-attached machine
```

`connect(name, password=None, timeout=5)` runs discovery, matches `name` case-insensitively (exact match first, then unique prefix/substring match), and returns a ready `Machine`. Raise `MachineNotFoundError` (include the list of names that *were* seen) and `AmbiguousMachineError` (multiple matches; include candidates) — never make the caller write selection code for the happy path.

## 3. Discovery (UDP, port 37020)

Verified protocol from `src/common/discovery.py`:

- All frames are binary UDP datagrams on port **37020**. First byte is the message type: `HELLO=1`, `FULL=2`, `PING=3`, `PONG=4`, `OFFLINE=5`.
- **HELLO**: `bytes([1, name_len]) + name_bytes` — name is UTF-8, max 32 bytes. A client broadcasts this to `255.255.255.255:37020`.
- **FULL**: `bytes([2, peer_count])` followed by, per peer: 4 raw IP bytes, 1 name-length byte, name bytes. The board with the lowest IP on the LAN acts as "registry" and answers HELLOs with a FULL frame listing all known boards.
- Clients don't need PING/PONG/OFFLINE; those are board-to-board liveness messages, but the parser must tolerate (skip) them arriving on the socket.

Client algorithm for `discover(timeout=5, name=None)`:

1. Open a UDP socket, `SO_REUSEADDR` + `SO_BROADCAST`, bind `0.0.0.0:37020` (fall back to an ephemeral port if 37020 is taken and note the caveat: the FULL reply is sent to the sender's address, so an ephemeral port still works).
2. Broadcast a HELLO with a client name (e.g. `"python-client"`).
3. Collect FULL frames until `timeout` expires (or until `name` is matched, for early exit in `connect()`). Re-broadcast HELLO every ~2 s while waiting.
4. Return `list[DiscoveredMachine]` — a small dataclass: `ip: str`, `name: str`. Deduplicate by IP; the registry may include itself.

Also expose `Machine.peers()` wrapping `GET /api/network/peers` — once you have one machine, its peer table (`{"192.168.4.243": {"name": "Pinbot", "self": true}}`) is an alternative discovery path that doesn't need broadcast (useful across VLANs where you know one IP).

## 4. The `Machine` object

`Machine` holds connection state and credentials, and is the single place users interact with a device:

```python
class Machine:
    transport: Transport          # HttpTransport or UsbTransport
    password: str | None          # for HMAC; settable after construction
    addresses: AddressMap         # named memory addresses (section 7)
    name: str | None              # from discovery or /api/game/name
```

Design rules:

- **Transport-agnostic.** Every API method goes through `self.transport.request(path, body=None, authenticated=False)`. HTTP and USB implement the same interface, so all wrappers work identically over both.
- **Thread-safe, serialized.** One lock per machine around the transport; the firmware cannot handle concurrent requests well and auth challenges are single-use.
- **Context manager.** `with warpedpinball.connect("elvira") as m:` closes sockets/serial ports on exit.
- `password` can be passed to `connect()`, set later (`m.password = "..."`), or read from env var `VECTOR_PASSWORD` as a fallback. Calling an authenticated route with no password raises `AuthenticationRequiredError` before any network traffic.

## 5. Authentication (HMAC-SHA256 challenge/response)

Verified against `require_auth` and `get_challenge` in `src/common/backend.py`:

1. `GET /api/auth/challenge` → `{"challenge": "<64 hex chars>"}`. Challenges expire after **60 seconds**, are **single-use** (deleted on successful auth), and the device holds at most ~10 outstanding challenges (`429 Too many challenges` beyond that — treat as retryable after a short sleep, since expired ones are purged on each challenge request).
2. Build `message = challenge + path + raw_body` where `path` is the URL path **without query string** (phew strips the query before storing `request.path`) and `raw_body` is the exact byte-for-byte body string you will send (empty string if none). Because the body must match exactly, the library must sign the *serialized* JSON string and send that same string — serialize once, sign it, send it.
3. `signature = hmac.new(password.encode(), message.encode(), hashlib.sha256).hexdigest()`.
4. Send the real request with headers `x-auth-challenge: <challenge>` and `x-auth-hmac: <signature>`.
5. On 401, raise `AuthenticationError` with the device's `{"error": reason}` detail. Distinguish "Challenge expired"/"Invalid challenge" (auto-retry once with a fresh challenge) from "Bad Credentials" (do not retry).

This whole dance lives in `auth.py` / the HTTP transport and is **invisible to users**: any method marked authenticated fetches a challenge, signs, and sends automatically.

Because challenges are single-use, fetch a challenge per request (do not cache). `Machine.verify_password()` wraps `/api/auth/password_check` so users can validate credentials up front.

**USB note:** requests arriving over the USB transport bypass HMAC entirely (the firmware trusts physical access — see `require_auth`). The USB transport therefore never signs; authenticated methods just work without a password over USB.

## 6. Transports

### 6.1 HTTP

- Base URL `http://<ip>` (port 80). Default timeout 10 s (configurable), no retries on mutating routes; idempotent GETs may retry once on connection errors.
- All request bodies are JSON with `Content-Type: application/json`. Note the firmware quirk: several routes documented with "body parameters" are fetched by the web UI as GETs with JSON bodies — the phew server parses `request.data` from the JSON body regardless of method, so the library should send bodies exactly as the web UI does (match `src/common/web/js` behavior if in doubt; sending POST with a JSON body works for all handlers since phew routes ignore method).
- Map non-2xx to typed exceptions: `AuthenticationError` (401), `CooldownError` (409/`"Already running"` and cooldown 429s — include a hint of the route's cooldown), `RateLimitedError` (429 on challenges), `VectorServerError` (500, body contains the handler error string).
- Streaming routes (`/api/memory-snapshot`, `/api/logs`, `/api/update/apply`) must stream, not buffer: expose them as iterators (see section 8).

### 6.2 USB serial

Verified against `src/common/usb_comms.py` and `docs/usb.md`:

- Serial 115200 baud. Request frame is one line: `route|header_text|body\n`, where `header_text` is HTTP-style `Name: value` lines separated by `\n`, and literal `|` in headers/body must be escaped as `\|`. Body parsing on-device requires `Content-Type: application/json` for JSON bodies.
- Response is a line prefixed `USB API RESPONSE-->` followed by JSON: `{"route": ..., "status": int, "headers": {...}, "body": "<string>"}`. The transport must skip unrelated console lines (the firmware prints logs to the same serial port), decode the JSON, and if `body` looks like JSON, parse it — then hand back the same `(status, headers, body)` shape as the HTTP transport.
- Open the port with a ~10 s read timeout and sleep ~2 s after opening (device may reset on connect). Provide `warpedpinball.list_serial_ports()` (via `serial.tools.list_ports`, filtered to Raspberry Pi VID `0x2E8A` when possible) and let `connect_usb()` auto-pick when exactly one candidate exists.
- No HMAC over USB (see 5). Streaming responses arrive fully rendered in the `body` field (the firmware joins generators before sending), so USB "streams" are just large single responses — document the memory implication.

## 7. Named memory addresses (`AddressMap`)

The firmware exposes raw SRAM access — `/api/address/read` (`{"offset": int, "count": int<=256}` → `{"offset": ..., "values": [0-255,...]}`) and `/api/address/write` (`{"offset": int, "values": [...]}`), both authenticated. Offsets are relative to `SRAM_DATA_BASE`. The device cannot store names, so the library does:

```python
m.addresses.define("mode_a_clock", 0x2134)                    # single byte
m.addresses.define("bonus", 0x2140, length=3)                 # multi-byte region
m.read("mode_a_clock")            # -> int (single byte) or bytes (length > 1)
m.write("mode_a_clock", 0x05)
m.read(0x2134)                    # raw offsets always still work
m.read_bytes(0x2000, count=64)    # bulk read, auto-chunked at 256 bytes
```

`AddressMap` details:

- A name maps to `(offset, length=1, encoding=None)`. Optional `encoding` hooks (`"bcd"`, `"le_uint"`, `"be_uint"`, or a `(decode, encode)` callable pair) let mod makers get ints out of multi-byte counters; default is raw.
- Serializable: `m.addresses.save("elvira.json")` / `AddressMap.load(path)` / pass `addresses=` to `connect()`. This is how a mod maker ships an address map for a specific game ROM alongside their code. Include the game's `/api/game/active_config` value in the saved file and warn on mismatch at load time.
- Reads/writes longer than 256 bytes are chunked transparently.

Also expose `m.memory_snapshot()` → `bytes` wrapping `/api/memory-snapshot` (full SRAM dump, streamed) — invaluable for *finding* addresses: take a snapshot, change something on the machine, diff. Consider a helper `m.diff_snapshots(a, b)` returning changed offsets.

## 8. High-level wrappers vs. raw escape hatch

### 8.1 Raw escape hatch (implement first — everything else is sugar)

```python
m.call("/api/version")                                   # GET-style, parsed JSON back
m.call("/api/player/update", body={"id": 0, "initials": "MSM"}, authenticated=True)
m.call_stream("/api/logs", authenticated=True)           # -> iterator of bytes chunks
```

`call()` handles auth signing, serialization, error mapping, and returns parsed JSON (or text when not JSON). Every route in `docs/routes.md` is reachable through it, so the library never blocks access to new/obscure firmware routes.

### 8.2 Clean wrappers

Group as plain methods (or light sub-namespaces like `m.scores.*` if the implementer prefers — keep it flat and obvious). Auth column per `docs/routes.md`:

| Method | Route | Auth |
|---|---|---|
| `m.version()` | `/api/version` | no |
| `m.machine_id()` | `/api/machine_id` | no |
| `m.game_name()` | `/api/game/name` | no |
| `m.game_status()` | `/api/game/status` | no |
| `m.reboot_game()` | `/api/game/reboot` (power-cycles the pinball machine) | yes |
| `m.reboot()` | `/api/settings/reboot` | yes |
| `m.leaderboard()` | `/api/leaders` | no |
| `m.tournament()` | `/api/tournament` | no |
| `m.reset_leaderboard()` / `m.reset_tournament()` | `/api/leaders/reset`, `/api/tournament/reset` | yes |
| `m.claimable_scores()` / `m.claim_score(initials, player_index, score)` | `/api/scores/claimable`, `/api/scores/claim` | no |
| `m.players()` / `m.update_player(id, initials, full_name=None)` | `/api/players`, `/api/player/update` | no / yes |
| `m.check_for_updates()` | `/api/update/check` (10 s cooldown) | no |
| `m.apply_update(url=None, progress=None)` | `/api/update/apply`; default `url` from `check_for_updates()`; `progress` callback receives each `{"log", "percent"}` line from the stream | yes |
| `m.date()` / `m.set_date(datetime)` | `/api/get_date`, `/api/set_date` (convert to/from RTC tuple) | no / yes |
| `m.wifi_status()` / `m.faults()` / `m.logs()` | `/api/wifi/status`, `/api/fault`, `/api/logs` | no / no / yes |
| `m.export_scores()` / `m.import_scores(data)` | `/api/export/scores`, `/api/import/scores` | no / yes |
| `m.adjustments()` / `m.capture_adjustments(index)` / `m.restore_adjustments(index)` / `m.name_adjustment(index, name)` | `/api/adjustments/*` | mixed, per routes.md |
| `m.peers()` | `/api/network/peers` | no |

Skip AP-mode setup routes (`/api/settings/set_vector_config`, `/api/available_ssids`) in v1 or hide them under `m.setup.*` — they only apply to unconfigured boards.

## 9. Proposed additional features

- **Polling helper for game events**: `m.watch_game(interval=1.0)` — a generator that polls `/api/game/status` and yields change events (game started/ended, ball changed, score deltas). This is the number-one thing mod makers will build by hand otherwise. Keep interval ≥ 0.5 s to be kind to the device.
- **Memory diff finder** (see section 7): snapshot/diff workflow to locate addresses interactively.
- **CLI** (`vector` entry point): `vector discover`, `vector status elvira`, `vector read elvira 0x2134`, `vector update elvira`. Thin layer over the library; great for smoke-testing hardware.
- **Address map registry convention**: document a `~/.warpedpinball/addressmaps/<active_config>.json` lookup so `connect()` can auto-load a community address map matching the machine's active config.
- **Typed dataclasses** for common payloads (`Score`, `Player`, `GameStatus`, `UpdateInfo`) with `raw` dict access preserved — nicer autocomplete without hiding fields.
- **`m.wait_until_reachable(timeout)`**: poll `/api/version` after `reboot()`/`apply_update()` so scripts can resume when the board returns.
- **Firmware-version gating**: record `m.version()` at connect; when a wrapper hits a 404 on old firmware, raise `UnsupportedFirmwareError` naming the minimum version rather than a generic error.
- **Async variant** (stretch goal): if using `httpx`, an `AsyncMachine` mirror is cheap and useful for tournament dashboards polling many machines; still serialize per machine.

## 10. Testing guidance

- Unit-test HMAC signing against a fixture: password `"test"`, challenge, path, body → known hex digest (compute with `hmac`/`hashlib`, same as the firmware).
- Fake transport implementing the Transport ABC for wrapper tests; golden-file the JSON shapes from `docs/routes.md` examples.
- Discovery: test FULL-frame decoding against hand-built byte strings including truncated/garbage frames and PING/PONG noise.
- USB: test frame escaping (`\|`), interleaved log lines before the `USB API RESPONSE-->` line, and JSON-in-string body decoding.
- Live testing target: https://vector.doze.dev (demo instance) for read-only routes.
