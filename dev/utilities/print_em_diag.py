#!/usr/bin/env python3

# Parse a diagnostics dump and print each game_history file like ScoreTrack.print_game_history_file
# from windows / linux terminal on saved disagnostic file download

import re
import struct
import sys

HEX_LINE = re.compile(r"^[0-9A-Fa-f]+$")


def parse_game_history_bytes(data):
    off = 0

    def need(n):
        if off + n > len(data):
            raise ValueError("unexpected end of data")

    def read(n):
        nonlocal off
        need(n)
        b = data[off : off + n]
        off += n
        return b

    if read(4) != b"GHDR":
        raise ValueError("GHDR not found")

    scores = [struct.unpack_from("<I", read(4))[0] for _ in range(4)]

    if read(4) != b"GHIX":
        raise ValueError("GHIX not found")
    gameHistoryIndex = struct.unpack("<I", read(4))[0]

    if read(4) != b"GHVL":
        raise ValueError("GHVL not found")
    sensor_data = [struct.unpack_from("<I", read(4))[0] for _ in range(gameHistoryIndex)]

    if read(4) != b"GHTM":
        raise ValueError("GHTM not found")
    time_data = [struct.unpack_from("<H", read(2))[0] for _ in range(gameHistoryIndex)]

    if read(4) != b"GEND":
        raise ValueError("GEND not found")

    return scores, gameHistoryIndex, sensor_data, time_data


def print_game_history_like_pico(name, data):
    try:
        scores, idx, sensor_data, time_data = parse_game_history_bytes(data)
    except Exception as e:
        print(f"Error parsing {name}: {e}")
        return

    print(f"GameHistory File: {name}")
    print(f"GameHistory Length: {idx}")
    print(f"Actual Scores: {scores}")
    print(f"{'Index':>5} {'Sensor Data':>26} {'Time':>12}")
    print("-" * 55)
    for i in range(idx):
        bits = format(sensor_data[i] & 0xFFFFFFFF, "032b")
        print(f"{i:>5} {bits} {time_data[i]:>8}")


def iter_sections(lines):
    """Yield (name, hexstring) for each ==== BEGIN <name> ==== ... ==== END <name> ===="""
    in_section = False
    name = None
    hex_parts = []
    for line in lines:
        s = line.strip()
        if s.startswith("==== BEGIN ") and s.endswith("===="):
            in_section = True
            name = s[len("==== BEGIN ") : -4].strip()
            hex_parts = []
            continue
        if s.startswith("==== END ") and s.endswith("===="):
            if in_section and name:
                yield name, "".join(hex_parts)
            in_section = False
            name = None
            hex_parts = []
            continue
        if in_section:
            if HEX_LINE.match(s):
                hex_parts.append(s)
            # else ignore non-hex lines inside section
    # no implicit yield at EOF


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "diagnostics.txt"
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    any_found = False
    for name, hexblob in iter_sections(lines):
        any_found = True
        try:
            data = bytes.fromhex(hexblob)
        except Exception as e:
            print(f"Error decoding hex for {name}: {e}")
            continue
        print_game_history_like_pico(name, data)
        print()  # spacer between files

    if not any_found:
        print("No sections found. Ensure the file contains '==== BEGIN /game_history*.dat ====' blocks.")


if __name__ == "__main__":
    main()
