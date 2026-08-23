# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Execution watchdog for Vector.

Two layers working together:

  1. Hardware WDT (machine.WDT): reboots the board if the whole VM hard-hangs
     (C-level deadlock, runaway IRQ). Max timeout on RP2 is ~8s and it can
     NEVER be stopped once armed, so it is fed from a machine.Timer IRQ.

  2. Mainline supervisor: the Timer IRQ only feeds the WDT while the
     cooperative scheduler (phew run_scheduled) has called beat() recently.
     A hung asyncio loop / permanently blocked mainline therefore also ends
     in a reboot - but with a tolerance long enough that legitimate blocking
     (wifi joins, update downloads) never trips it.

Updates are exempt: while phew's _halt_schedule flag is set (update in
progress, mainline deliberately blocked for long stretches) the WDT is fed
unconditionally, so a reboot can never corrupt a flash update.
"""

import time

import machine

# Master switch - set True for field builds.
# Left False for bench work: once the hardware WDT is armed it cannot be
# stopped, so a Ctrl-C REPL session longer than MAINLINE_LIMIT_MS would end
# in a spontaneous reboot (call watchdog.hold() from the REPL to prevent it).
ENABLE = False

MAINLINE_LIMIT_MS = 180_000  # reboot if the scheduler is silent this long
_FEED_PERIOD_MS = 2_000

_wdt = None
_timer = None
_phew_server = None
_last_beat_ms = 0
_hold = False


def beat():
    """Called by the scheduler loop to prove mainline Python is alive."""
    global _last_beat_ms
    _last_beat_ms = time.ticks_ms()


def hold():
    """Bench escape hatch: feed unconditionally from now on.

    Call from the REPL right after Ctrl-C to keep an armed WDT from
    rebooting the board mid-debug-session.
    """
    global _hold
    _hold = True


def _tick(_):
    # IRQ context - keep this tiny and allocation-free
    if _wdt is None:
        return
    if _hold:
        _wdt.feed()
        return
    # updates halt the schedule and can legitimately block mainline for
    # minutes - feed unconditionally so a reboot never interrupts a flash write
    if _phew_server is not None and _phew_server._halt_schedule:
        _wdt.feed()
        return
    if time.ticks_diff(time.ticks_ms(), _last_beat_ms) < MAINLINE_LIMIT_MS:
        _wdt.feed()
    # else: stop feeding - the hardware WDT reboots the board within ~8s


def start():
    """Arm the watchdog. Call once, after the server loop is about to run."""
    global _wdt, _timer, _phew_server
    if not ENABLE or _wdt is not None:
        return
    from phew import server as _srv

    _phew_server = _srv
    beat()
    _wdt = machine.WDT(timeout=8000)
    _timer = machine.Timer()
    _timer.init(period=_FEED_PERIOD_MS, mode=machine.Timer.PERIODIC, callback=_tick)
    print("WATCHDOG: hardware WDT armed, mainline limit", MAINLINE_LIMIT_MS, "ms")
