#!/usr/bin/env python3
"""Demo script showing how to call the USB API using :mod:`usb_coms`.

This example sends an unauthenticated request to ``/api/game/status`` followed
by an authenticated call to ``/api/auth/password_check`` using the helper
functions from :class:`usb_coms.UsbApiClient`.

Usage::

    python dev/usb_coms_demo.py
"""

import time

from dev.usb_coms import UsbApiClient


def main():
    # Open a serial connection to the device. Adjust the port if needed for your
    # environment (for example, ``COM3`` on Windows).
    client = UsbApiClient.from_device()

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
