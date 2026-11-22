# This file is part of the Warped Pinball Vector (Whitestar) Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0

"""
Switch monitoring module - Whitestar (Switches Type 40)

Whitestar games keep their own switch health tables in battery RAM: the
data behind the test menu's TECHNICIAN ALERTS ("SWITCH STUCK OPEN" /
"SWITCH STUCK CLOSED"). Vector never counts switch hits itself here; it
reads those tables and adds what the game cannot tell a service person:
whether a switch that was in the game's last report has worked since.

Game tables (one byte per column, bit = row, switch = index + 1):
    Address + 0  ..  +7   cur_nc   not closed yet in the current 50 game period
    Address + 8  .. +15   cur_st   not opened yet in the current period (stuck closed)
    Address + 16 .. +23   rep_nc   report: never closed in the previous period
    Address + 24 .. +31   rep_st   report: stuck closed in the previous period
    CounterAdr            games played in the current period, BCD 0-49

At the 50th game the game copies cur_* to rep_*, clears the counter and
reloads cur_* from its ROM mask of monitored switches. Older games (Apollo
13 .. Monopoly) also clear a switch's report bit as soon as it works again;
later games (High Roller Casino, Playboy, RollerCoaster Tycoon onward)
keep the report frozen until the next rollover.

Vector keeps a snapshot of the report taken at the last rollover it saw, in
the 72 byte "switches" FRAM record, and compares the live tables with it:
    flagged in the snapshot and still flagged now   -> still bad
    flagged in the snapshot and hit since           -> fixed
That gives the same answer on both kinds of game.

Snapshot record:
    0-7    snap_nc   copy of rep_nc at the last rollover seen
    8-15   snap_st   copy of rep_st at the last rollover seen
    16     last_games  games counter at the last poll (binary 0-49)
    17     magic 0x40 (missing = not a Type 40 snapshot, initialise)
    18-71  reserved (0)

The results fit the existing admin page unchanged: each switch is reported
as row / col / val / label, the colour comes from val, and the state is
written into the label so the page's tooltip and info panel explain it
(e.g. "Spinner - working again"). Nothing is ever written to the game; a
repaired switch turns green as soon as the game clears its bit, on the next
Refresh of the page.

Same public API as the common Switches module (initialize, poll_switches,
save_switches, get_switch_index, subscribe, unsubscribe, get_diagnostics).
See ConfigTools/Whitestar/WHITESTAR_SWITCH_DIAGNOSTICS.md.

Note: MicroPython uses cooperative multitasking (single-threaded event loop).
Scheduled tasks don't preempt each other, so no synchronization is needed.
"""
import SPI_DataStore
import DataMapper
import SharedState as S
from logger import logger_instance
log = logger_instance

SWITCH_TYPE = 40
SNAP_MAGIC = 0x40
SNAP_LENGTH = 72
IDX_LAST_GAMES = 16
IDX_MAGIC = 17
PERIOD_GAMES = 50

# one byte changes once per game, 30 seconds is plenty
POLL_WS_SWITCHES_mS = 30000

#switch system enable
switch_system_on = False

# RAM copy of the FRAM snapshot record
_snap = bytearray(SNAP_LENGTH)

# Switch subscription system (kept for API compatibility with Formats / Golf)
switch_subscriptions = {}


# ---------------------------------------------------------------------------
# snapshot record
# ---------------------------------------------------------------------------
def _load_snapshot():
    global _snap
    record = SPI_DataStore.read_record("switches")
    data = bytes(record.get("switches", [0] * SNAP_LENGTH))[:SNAP_LENGTH]
    _snap = bytearray(data) + bytearray(SNAP_LENGTH - len(data))


def _save_snapshot():
    try:
        SPI_DataStore.write_record("switches", {"switches": list(_snap)})
    except Exception as e:
        log.log(f"SWITCHES: Error saving snapshot: {e}")


def _snapshot_valid():
    return _snap[IDX_MAGIC] == SNAP_MAGIC


def _take_snapshot(rep_nc, rep_st, games):
    """Copy the game's report tables into the snapshot (flags are kept by the caller)."""
    _snap[0:8] = rep_nc
    _snap[8:16] = rep_st
    _snap[IDX_LAST_GAMES] = games
    _snap[IDX_MAGIC] = SNAP_MAGIC
    for i in range(IDX_MAGIC + 1, SNAP_LENGTH):
        _snap[i] = 0
    _save_snapshot()


# ---------------------------------------------------------------------------
# public API shared with the common module
# ---------------------------------------------------------------------------
def initialize():
    """
    Load the snapshot from FRAM and start the rollover poll.
    Should be called once at startup.
    """
    global switch_system_on

    switch_type = S.gdata.get("Switches", {}).get("Type")
    if switch_type != SWITCH_TYPE or not DataMapper.switches_supported():
        log.log("SWITCHES: Invalid or missing 'Switches'")
        switch_system_on = False
        return False

    try:
        _load_snapshot()
        if _snapshot_valid():
            log.log(f"SWITCHES: snapshot loaded, {_snap[IDX_LAST_GAMES]} games into the period")
        else:
            log.log("SWITCHES: no snapshot yet, will take one from the game's report")
        switch_system_on = True

        from phew.server import schedule
        schedule(poll_switches, 15000, POLL_WS_SWITCHES_mS)
        return True
    except Exception as e:
        log.log(f"SWITCHES: Error loading switch snapshot: {e}")
        switch_system_on = False
    return False


def poll_switches():
    """
    Rollover detection. Called every 30 seconds.

    The games counter restarts at 0 when the game rolls its tables over, so
    a counter lower than the one seen at the last poll means a new report
    exists: snapshot it. Vector being off for 50 or more games can hide a
    rollover (the counter comes back higher); that one is missed until the next.
    """
    if switch_system_on is False:
        return
    try:
        tables = DataMapper.get_switch_tables()
        if tables is None:
            return
        cur_nc, cur_st, rep_nc, rep_st, games = tables
        if not 0 <= games < PERIOD_GAMES:
            return  # not valid BCD yet (power-up), try later

        if not _snapshot_valid():
            _take_snapshot(rep_nc, rep_st, games)
            log.log("SWITCHES: first snapshot of the game's switch report")
        elif games < _snap[IDX_LAST_GAMES]:
            _take_snapshot(rep_nc, rep_st, games)
            log.log("SWITCHES: rollover, new switch report snapshot")
        elif games != _snap[IDX_LAST_GAMES]:
            _snap[IDX_LAST_GAMES] = games  # RAM only, saved with the next snapshot
    except Exception as e:
        log.log(f"SWITCHES: Error in poll_switches: {e}")


def save_switches():
    """Save the snapshot to SPI storage."""
    _save_snapshot()


def get_switch_index(switch_name):
    """
    Translate a switch name to its index (0-63), -1 if not found.
    """
    if not switch_system_on:
        return -1
    try:
        names = S.gdata.get("Switches", {}).get("Names")
        if not names:
            return -1
        for idx, entry in enumerate(names):
            name = entry[0] if isinstance(entry, list) and entry else entry
            if name == switch_name:
                return idx
        return -1
    except Exception as e:
        log.log(f"SWITCHES: Error in get_switch_index: {e}")
        return -1


def subscribe(switch_name, callback):
    """
    Subscribe to a switch trigger event (name or index).

    Whitestar keeps no per-switch activity bytes, only the once-per-period
    health bits, so callbacks are never raised on this platform. The
    subscription is recorded so callers (Formats / Golf) behave as elsewhere.
    """
    global switch_subscriptions

    if not callable(callback):
        log.log("SWITCHES: subscribe() - callback must be callable")
        return False

    if isinstance(switch_name, int):
        switch_index = switch_name
        max_switch_index = S.gdata.get("Switches", {}).get("Length", -1)
        if switch_index < 0 or switch_index > max_switch_index:
            log.log(f"SWITCHES: subscribe() - invalid switch index {switch_index}")
            return False
    else:
        switch_index = get_switch_index(switch_name)
        if switch_index < 0:
            log.log(f"SWITCHES: subscribe() - invalid switch name '{switch_name}'")
            return False

    if switch_index not in switch_subscriptions:
        switch_subscriptions[switch_index] = []

    if callback not in switch_subscriptions[switch_index]:
        switch_subscriptions[switch_index].append(callback)
        log.log(f"SWITCHES: Subscribed to switch '{switch_name}' (index {switch_index}) - no hit events on Whitestar")
        return True

    return False


def unsubscribe(switch_name, callback):
    """
    Unsubscribe from a switch trigger event (name or index).
    """
    global switch_subscriptions

    if isinstance(switch_name, int):
        switch_index = switch_name
        if switch_index < 0 or switch_index >= 72:
            log.log(f"SWITCHES: unsubscribe() - invalid switch index {switch_index}")
            return False
    else:
        switch_index = get_switch_index(switch_name)
        if switch_index < 0:
            log.log(f"SWITCHES: unsubscribe() - invalid switch name '{switch_name}'")
            return False

    if switch_index not in switch_subscriptions:
        return False

    if callback in switch_subscriptions[switch_index]:
        switch_subscriptions[switch_index].remove(callback)
        log.log(f"SWITCHES: Unsubscribed from switch '{switch_name}' (index {switch_index})")
        if not switch_subscriptions[switch_index]:
            del switch_subscriptions[switch_index]
        return True

    return False


def get_diagnostics():
    """
    Diagnostic information for every monitored switch.

    Returns a list of dicts with row, col, val (0-100) and label, the fields
    the admin page shows. The label carries the switch number (the page's
    cells show column/row, the Whitestar manuals use 1-64) and, when the
    switch is not plain OK, its state, so the tooltip and info panel read:
        "Sw 25 Spinner"                          OK
        "Sw 25 Spinner - working again"          in the game's report, has worked since
        "Sw 25 Spinner - stuck closed 62 games"  in the report and still stuck
        "Sw 25 Spinner - not hit in 62 games"    in the report and still not hit
        "Sw 25 Spinner - not opened in 12 games" current period only
        "Sw 25 Spinner - not hit in 12 games"    current period only

    val uses the Data East scale (100 - 2 x games) so the page's colours
    work: red at 0, yellow below 50, green otherwise.

    The extra fields num, state, text and games are ignored by the page and
    kept for tools.
    """
    if not switch_system_on:
        return []

    diagnostics = []
    try:
        names = S.gdata["Switches"].get("Names") or []
        tables = DataMapper.get_switch_tables()
        if tables is None:
            return []
        cur_nc, cur_st, rep_nc, rep_st, games = tables
        n = games if 0 <= games < PERIOD_GAMES else 0

        # no snapshot yet: the live report stands in for it
        if _snapshot_valid():
            snap_nc, snap_st = _snap[0:8], _snap[8:16]
        else:
            snap_nc, snap_st = rep_nc, rep_st

        for i in range(min(64, len(names))):
            entry = names[i]
            if not entry or not isinstance(entry, list) or not entry[0]:
                continue
            c, m = i // 8, 1 << (i % 8)
            now_nc = cur_nc[c] & m
            now_st = cur_st[c] & m
            was_nc = snap_nc[c] & m
            was_st = snap_st[c] & m

            if was_st and now_st:
                state, val, text = "stuck", 0, f"stuck closed {PERIOD_GAMES + n} games"
            elif was_nc and now_nc:
                state, val, text = "dead", 0, f"not hit in {PERIOD_GAMES + n} games"
            elif (was_nc and not now_nc) or (was_st and not now_st):
                state, val, text = "fixed", 100, "working again"
            elif now_st:
                state, val, text = "stuck", max(0, 100 - 2 * n), f"not opened in {n} games"
            elif now_nc:
                state, val, text = "open", max(0, 100 - 2 * n), f"not hit in {n} games"
            else:
                state, val, text = "ok", 100, "OK"

            # right after a rollover every switch is "not hit in 0 games": not worth saying
            label = f"Sw {i + 1} {entry[0].strip()}"
            if state != "ok" and not (state in ("open", "stuck") and n == 0):
                label += " - " + text

            diagnostics.append({
                "row": i % 8 + 1,
                "col": i // 8 + 1,
                "val": val,
                "label": label,
                "num": i + 1,
                "state": state,
                "text": text,
                "games": n,
            })
    except Exception as e:
        log.log(f"SWITCHES: Error in get_diagnostics: {e}")
        return []

    return diagnostics
