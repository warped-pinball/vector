"""
WiFi and admin passwords longer than the configuration record can hold.

The configuration record has 32 bytes for the WiFi password and 16 for the
admin password. WPA allows 63 characters (or a 64 digit hex key), and people
want longer admin passwords too, so each can be up to 64 bytes. The whole
password lives in its own record below the rest of the data store
("wifi_password", "admin_password"). The configuration record still gets as
much as fits, so firmware from before these records existed keeps working
with short passwords, and nothing has to be migrated.

A long record is only trusted when its marker is there and its check matches
the configuration record it was saved with. Anything else (a board that never
had one, uninitialised FRAM, or settings saved since by older firmware) falls
back to the configuration record's own password.
"""

from hashlib import sha256

import SPI_DataStore as DataStore

MAX_BYTES = 64

# kind: (long record, configuration field, bytes the field holds, marker)
_KINDS = {
    "wifi": ("wifi_password", "password", 32, b"WPL1"),
    "admin": ("admin_password", "Gpassword", 16, b"APL1"),
}


def _check(ssid, short_password, password):
    """4 bytes tying a long record to the configuration record it belongs to"""
    h = sha256()
    h.update(ssid.encode())
    h.update(b"\0")
    h.update(short_password.encode())
    h.update(b"\0")
    h.update(password.encode())
    return h.digest()[:4]


def short_password(password, max_bytes):
    """The part of password that fits max_bytes, cut on a character boundary"""
    data = password.encode()
    if len(data) <= max_bytes:
        return password
    cut = max_bytes
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
    """Write the configuration record, and a long record for each password that needs one.

    Raises OSError when a write fails, so setup can say so instead of rebooting.
    """
    config = {"ssid": ssid, "gamename": gamename}
    # the long records first: if one fails, the configuration has not changed yet
    for kind, full in (("wifi", password), ("admin", admin_password)):
        record_name, field, field_bytes, marker = _KINDS[kind]
        short = short_password(full, field_bytes)
        config[field] = short
        if short == full:
            # fits the old field: clear the long record so a stale one can never apply
            _write(record_name, {"marker": b"", "check": b"", "password": b""})
        else:
            _write(record_name, {"marker": marker, "check": _check(ssid, short, full), "password": full.encode()})
    _write("configuration", config)


def read_password(kind, configuration=None):
    """The whole WiFi ("wifi") or admin ("admin") password"""
    if configuration is None:
        configuration = DataStore.read_record("configuration", 0)
    record_name, field, _field_bytes, marker = _KINDS[kind]
    short = configuration[field]
    try:
        record = DataStore.read_record(record_name, 0)
        if record["marker"] != marker:
            return short
        password = record["password"].decode()
        if password.startswith(short) and record["check"] == _check(configuration["ssid"], short, password):
            return password
    except Exception:
        pass
    return short


def passwords_to_try(kind, configuration=None):
    """The passwords to accept or connect with, best first.

    Usually just one. When the long record applies, the configuration record's own
    password follows it: older firmware saving the same network with a password
    that happens to equal the long one's first bytes leaves a record that still
    matches, and only trying both tells those apart.
    """
    if configuration is None:
        configuration = DataStore.read_record("configuration", 0)
    short = configuration[_KINDS[kind][1]]
    password = read_password(kind, configuration)
    if password == short:
        return [password]
    return [password, short]
