"""
WiFi passwords longer than the configuration record can hold.

The configuration record has 32 bytes for the WiFi password, but WPA allows
63 characters (or a 64 digit hex key). The whole password lives in its own
"wifi_password" record below the rest of the data store. The configuration
record still gets the first 32 bytes, so firmware from before this record
existed keeps working with short passwords, and nothing has to be migrated.

The long record is only trusted when its marker is there and its check
matches the configuration record it was saved with. Anything else (a board
that never had one, uninitialised FRAM, or settings saved since by older
firmware) falls back to the configuration record's own password.
"""

from hashlib import sha256

import SPI_DataStore as DataStore

MAX_BYTES = 64
_SHORT_BYTES = 32
_MARKER = b"WPL1"


def _check(ssid, short_password, password):
    """4 bytes tying the long record to the configuration record it belongs to"""
    h = sha256()
    h.update(ssid.encode())
    h.update(b"\0")
    h.update(short_password.encode())
    h.update(b"\0")
    h.update(password.encode())
    return h.digest()[:4]


def short_password(password):
    """The part of password that fits the configuration record, cut on a character boundary"""
    data = password.encode()
    if len(data) <= _SHORT_BYTES:
        return password
    cut = _SHORT_BYTES
    # never split a multi byte UTF-8 character: the record is decoded on every read
    while cut > 0 and (data[cut] & 0xC0) == 0x80:
        cut -= 1
    return data[:cut].decode()


def _write(structure_name, record):
    # write_record reports a FRAM failure by returning an error instead of raising
    result = DataStore.write_record(structure_name, record)
    if result is not None:
        raise OSError(result.get("message", f"could not write {structure_name}"))


def save_configuration(ssid, password, gamename, admin_password):
    """Write the configuration record, and the long password record when the password needs it.

    Raises OSError when a write fails, so setup can say so instead of rebooting.
    """
    short = short_password(password)
    # the long record first: if it fails, nothing has changed yet
    if short == password:
        # fits the old field: clear the long record so a stale one can never apply
        _write("wifi_password", {"marker": b"", "check": b"", "password": b""})
    else:
        _write("wifi_password", {"marker": _MARKER, "check": _check(ssid, short, password), "password": password.encode()})
    _write(
        "configuration",
        {
            "ssid": ssid,
            "password": short,
            "Gpassword": admin_password,
            "gamename": gamename,
        },
    )


def read_password(configuration=None):
    """The WiFi password to connect with"""
    if configuration is None:
        configuration = DataStore.read_record("configuration", 0)
    short = configuration["password"]
    try:
        record = DataStore.read_record("wifi_password", 0)
        if record["marker"] != _MARKER:
            return short
        password = record["password"].decode()
        if password.startswith(short) and record["check"] == _check(configuration["ssid"], short, password):
            return password
    except Exception:
        pass
    return short


def passwords_to_try(configuration=None):
    """The passwords to connect with, best first.

    Usually just one. When the long record applies, the configuration record's own
    password follows it: older firmware saving the same network with a password
    that happens to equal the long one's first 32 bytes leaves a record that still
    matches, and only trying both tells those apart.
    """
    if configuration is None:
        configuration = DataStore.read_record("configuration", 0)
    password = read_password(configuration)
    if password == configuration["password"]:
        return [password]
    return [password, configuration["password"]]
