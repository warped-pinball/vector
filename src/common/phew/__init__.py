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
        wlan.config(pm=0xA11140)  # disable power save; dozing radio drops packets
        wlan.connect()
    except Exception as e:
        logging.error(f"Failed to reconnect to wifi: {e}")


# A name set by hand lives in the unused extras "message" field, marked so a
# board's old "ok"/"none" there is not mistaken for one. 20 bytes, so 18 for the name.
_NAME_MARK = "H:"
_NAME_MAX = 18


def _clean_hostname(name):
    """A DHCP host name is letters, digits and hyphens only."""
    return "".join(c for c in str(name).upper() if "A" <= c <= "Z" or "0" <= c <= "9" or c == "-").strip("-")


def hostname_override():
    """The name set by hand on the admin page, or "" for the automatic one."""
    from SPI_DataStore import read_record

    message = read_record("extras", 0).get("message", "")
    return message[len(_NAME_MARK) :] if message.startswith(_NAME_MARK) else ""


def set_hostname_override(name):
    """Store a name set by hand, cleaned; blank (or nothing usable) goes back to automatic. Returns what was stored."""
    from SPI_DataStore import read_record, write_record

    name = _clean_hostname(name)[:_NAME_MAX]
    info = read_record("extras", 0)
    info["message"] = _NAME_MARK + name if name else ""
    write_record("extras", info, 0)
    return name


def _em_abbrev(game_name):
    """An EM has no config to carry an Abbrev, so use the name its owner typed.

    Initials of a name of several words ("Gottlieb Fireball" -> GF), or a
    one-word name itself, up to 10 characters ("Fireball" -> FIREBALL). The
    names an EM board starts with mean nobody has named it, so those get the
    MAC fallback.
    """
    words = "".join(c if "A" <= c <= "Z" or "0" <= c <= "9" else " " for c in str(game_name).upper()).split()
    if not words or " ".join(words) in ("EM GAME", "EM", "EM MACHINE"):
        return ""
    return words[0][:10] if len(words) == 1 else "".join(w[0] for w in words)


def default_hostname():
    """WP-<abbreviation>, e.g. WP-TNG, from the game config's GameInfo "Abbrev",
    or for an EM from the game name its owner typed.

    A config without one, or no game picked yet, falls back to the last 3
    bytes of the wifi MAC (WP-1A2B3C), which is at least unique on the network.
    """
    from binascii import hexlify

    import network
    import SharedState

    info = SharedState.gdata.get("GameInfo", {})
    abbrev = _clean_hostname(info.get("Abbrev", ""))
    if not abbrev and info.get("System") == "EM":
        abbrev = _em_abbrev(info.get("GameName", ""))
    if abbrev:
        return ("WP-" + abbrev)[:32]

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)  # the MAC is only read from the chip once it is up
    return "WP-" + hexlify(wlan.config("mac")[3:]).decode().upper()


def dhcp_hostname():
    """The name this board gives the router: one set by hand, else the default."""
    return hostname_override() or default_hostname()


def set_dhcp_hostname():
    """Give the router this board's name rather than the firmware's "Pico2W".

    MicroPython keeps the name in RAM and lwIP reads it every time it builds
    a DHCP request, so this has to run on every boot, before the first
    connect: a power cycle puts the firmware default back.
    """
    import network

    try:
        name = dhcp_hostname()
        network.hostname(name)
        print(f"DHCP hostname: {name}")
    except Exception as e:
        print(f"Could not set the DHCP hostname: {e}")


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

    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.config(pm=0xA11140)  # disable power save; dozing radio drops packets
        wlan.connect(ssid, password)
        start = time.ticks_ms()
        status = wlan.status()

        unknown_status = f"unknown status {status}"
        logging.debug(f"  - {statuses.get(status, unknown_status)}")  # got '2' as status sometimes
        while not wlan.isconnected() and time.ticks_diff(time.ticks_ms(), start) < (timeout_seconds * 1000):
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
    except Exception as e:
        # A wedged/stalled cyw43 chip can raise here (e.g. OSError from
        # wlan.connect()/status()/isconnected() while the driver is stuck) -
        # log it to persistent (FRAM) storage rather than letting it propagate
        # as an unlogged traceback, since that's otherwise lost on reboot.
        logging.error(f"CYW43 fault during wifi connect: {e}")
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
