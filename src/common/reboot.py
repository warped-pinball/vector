"""Utility to reboot the host after a short delay.

This allows HTTP handlers to schedule a reboot after their
response has been sent.
"""

from time import sleep
from machine import reset as machine_reset
from phew.server import schedule

try:
    import reset_control
except ImportError:
    reset_control = None


def schedule_reboot(delay_ms: int = 100, hold_ms: int = 2000) -> None:
    """Schedule a device reboot.

    Parameters
    ----------
    delay_ms: int
        Time in milliseconds before the reboot sequence starts.
    hold_ms: int
        How long to hold the pinball machine in reset before the
        microcontroller is reset.
    """

    def _reboot():
        if reset_control is not None:
            try:
                reset_control.reset()
            except Exception as e:
                print(f"reboot: error resetting machine: {e}")
        sleep(hold_ms / 1000)
        machine_reset()

    schedule(_reboot, delay_ms, log="Server: scheduled reboot")
