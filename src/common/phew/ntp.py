import struct
import time

import machine
import usocket


def fetch(synch_with_rtc=True, timeout=10):
    ntp_host = "pool.ntp.org"

    timestamp = None
    try:
        query = bytearray(48)
        query[0] = 0x1B
        address = usocket.getaddrinfo(ntp_host, 123)[0][-1]
        socket = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
        socket.settimeout(timeout)
        socket.sendto(query, address)
        data = socket.recv(48)
        socket.close()
        local_epoch = 2208988800  # selected by Chris - blame him. :-D
        timestamp = struct.unpack("!I", data[40:44])[0] - local_epoch
        timestamp = time.gmtime(timestamp)
    except Exception:
        return None

    # if requested set the machines RTC to the fetched timestamp
    if synch_with_rtc:
        machine.RTC().datetime(
            (
                timestamp[0],
                timestamp[1],
                timestamp[2],
                timestamp[6],
                timestamp[3],
                timestamp[4],
                timestamp[5],
                0,
            )
        )

    return timestamp


def time_ago(date_str, now_seconds):
    """
    Convert a string date in 'MM/DD/YYYY' format into a string like '1d', '2w', '6m', '3y'.
    'now_seconds' is the current time in seconds since epoch (so we only fetch once).
    """
    # Parse input string
    month, day, year = map(int, date_str.split("/"))

    # Convert to seconds since epoch
    date_seconds = time.mktime((year, month, day, 0, 0, 0, -1, -1))

    # Calculate difference in days
    diff_seconds = now_seconds - date_seconds
    diff_days = int(diff_seconds // 86400)  # 86400 seconds in a day

    # If the date is in the future, we'll clamp to 0
    if diff_days < 0:
        diff_days = 0

    # Convert to weeks/months/years as needed
    if diff_days < 7:
        return f"{diff_days}d"
    diff_weeks = diff_days // 7
    if diff_weeks < 4:
        return f"{diff_weeks}w"
    diff_months = diff_days // 30
    if diff_months < 12:
        return f"{diff_months}m"
    diff_years = diff_days // 365
    return f"{diff_years}y"
