# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Non-blocking stdout for USB serial.

When the host PC stops draining the USB CDC serial (e.g. it goes to sleep),
MicroPython's built-in print() blocks the cooperative scheduler waiting for
TX FIFO space. Importing this module replaces the built-in print() with a
version that drops output when the host isn't reading, so the Pico keeps
running normally and never stacks up a backlog.

Delivery-critical traffic (the USB API responses in usb_comms) must NOT be
dropped while the host is awake, so it uses reliable_print() instead, which
keeps the original (blocking, but bounded by the firmware CDC TX timeout)
behavior.

Import this FIRST in main.py so every later print() is covered.
"""
import builtins
import sys
import uselect

# Capture the native (blocking) print before we override it. Used for
# delivery-critical output that must arrive intact while the host is awake.
reliable_print = builtins.print

_stdout = sys.stdout
_poll = uselect.poll()
_poll.register(_stdout, uselect.POLLOUT)
_CHUNK = 64


def safe_print(*args, sep=" ", end="\n"):
    """Fire-and-forget print: drop output if the USB host isn't draining."""
    try:
        msg = sep.join(str(a) for a in args) + end
    except Exception:
        return
    i = 0
    n = len(msg)
    while i < n:
        if not _poll.poll(0):  # TX FIFO full -> host not reading, drop remainder
            return
        try:
            written = _stdout.write(msg[i:i + _CHUNK])
        except Exception:
            return
        if not written:
            return
        i += written


# Install the non-blocking print globally for every bare print() in the project.
builtins.print = safe_print
