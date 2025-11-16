#!/usr/bin/env python3
"""Demo script showing how to call the USB API using :mod:`usb_coms`.

This example sends an unauthenticated request to ``/api/game/status`` followed
by an authenticated call to ``/api/auth/password_check`` using the helper
functions from :class:`usb_coms.UsbApiClient`.

Usage::

    python dev/usb_coms_demo.py
"""

import sys
import time
from pathlib import Path

# Ensure the repository root is on ``sys.path`` so ``dev`` can be imported when the
# script is executed directly via ``python dev/usb_coms_demo.py``.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dev.usb_coms import UsbApiClient

# For demo purposes we hard-code the device password here. In production you
# should load this value from a secure secret store or environment variable.
DEVICE_PASSWORD = "vector-password"


def main():
    # Open a serial connection to the device. Adjust the port if needed for your
    # environment (for example, ``COM3`` on Windows).
    client = UsbApiClient.from_device(device_password=DEVICE_PASSWORD)

    try:
        print("Listening for responses. Press Ctrl+C to stop.")
        while True:
            client.send_and_receive(
                route="/api/game/status",
                payload={"player": "AB|C", "score": 12345},
            )
            time.sleep(5)

            client.send_authenticated_request(
                route="/api/auth/password_check",
                payload={"intent": "demo"},
            )
            time.sleep(5)
    except KeyboardInterrupt:
        print("Stopped listening.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
