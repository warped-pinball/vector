__version__ = "0.0.2"

# highly recommended to set a lowish garbage collection threshold
# to minimise memory fragmentation as we sometimes want to
# allocate relatively large blocks of ram.
import gc
import os

# phew! the Pico (or Python) HTTP Endpoint Wrangler
from . import logging

gc.threshold(50000)


# determine if remotely mounted or not, changes some behaviours like
# logging truncation
remote_mount = False
try:
    os.statvfs(".")  # causes exception if remotely mounted (mpremote/pyboard.py)
except Exception:
    remote_mount = True


def get_ip_address():
    import network

    try:
        return network.WLAN(network.STA_IF).ifconfig()[0]
    except Exception:
        return None


def is_connected_to_wifi():
    import network

    wlan = network.WLAN(network.STA_IF)
    return wlan.isconnected()


def reconnect_to_wifi():
    if is_connected_to_wifi():
        return
    import network

    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect()
    except Exception as e:
        logging.error(f"Failed to reconnect to wifi: {e}")


# helper method to quickly get connected to wifi
def connect_to_wifi(ssid, password, timeout_seconds=30):
    import time

    import network

    statuses = {
        network.STAT_IDLE: "idle",
        network.STAT_CONNECTING: "connecting",
        network.STAT_WRONG_PASSWORD: "wrong password",
        network.STAT_NO_AP_FOUND: "access point not found",
        network.STAT_CONNECT_FAIL: "connection failed",
        network.STAT_GOT_IP: "got ip address",
    }

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    start = time.ticks_ms()
    status = wlan.status()

    logging.debug(f"  - {statuses.get(status, 'unknown status')}")  # got '2' as status sometimes
    while not wlan.isconnected() and (time.ticks_ms() - start) < (timeout_seconds * 1000):
        new_status = wlan.status()
        if status != new_status:
            logging.debug(f"  - {statuses.get(new_status, 'unknown status')}")
            status = new_status
        time.sleep(0.25)

    mac = wlan.config("mac")
    mac_address = ":".join("{:02x}".format(b) for b in mac)
    print("Server:  MAC Address ", mac_address)

    if wlan.status() == network.STAT_GOT_IP:
        return wlan.ifconfig()[0]
    return None


# helper method to put the pico into access point mode
def access_point(ssid, password=None):
    import network

    # start up network in access point mode
    wlan = network.WLAN(network.AP_IF)
    wlan.config(essid=ssid)
    if password:
        wlan.config(password=password)
    else:
        wlan.config(security=0)  # disable password
    wlan.active(True)

    return wlan
