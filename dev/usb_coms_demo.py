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

def main():
    # Open a serial connection to the device. Adjust the port if needed for your
    # environment (for example, ``COM3`` on Windows).
    client = UsbApiClient.from_device(
        # Authentication is disabled for USB traffic because the physical cable
        # is treated as a trusted link. If your device firmware enforces HMAC
        # auth, set ``authentication_enabled=True`` and provide a password.
        authentication_enabled=False,
    )

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
                require_authentication=False,
            )
            time.sleep(5)
    except KeyboardInterrupt:
        print("Stopped listening.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
