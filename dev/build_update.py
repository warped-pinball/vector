#!/usr/bin/env python3

import os
import json
import base64
from pathlib import Path

BUILD_DIR = "build"
SOURCE_DIR = "src"
OUTPUT_FILE = "update.json"
DEFAULT_CHUNK_SIZE = 1024  # Default chunk size in bytes

def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

def crc16(data: bytes) -> str:
    return "{:04X}".format(crc16_ccitt(data))

def get_file_contents(file_path: str) -> bytes:
    with open(file_path, "rb") as f:
        return f.read()

def split_into_chunks(data: bytes, chunk_size: int) -> list[bytes]:
    """Split data into chunks of a given size."""
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

def build_update_json(build_dir: str, output_file: str, version: str, chunk_size: int):
    update_data = []

    for root, _, files in os.walk(build_dir):
        for file_name in files:
            file_path = Path(root) / file_name
            relative_path = os.path.relpath(file_path, build_dir)

            contents = get_file_contents(file_path)

            # Base64 encode all file contents
            encoded_contents = base64.b64encode(contents)

            # Split into chunks
            chunks = split_into_chunks(encoded_contents, chunk_size)

            cumulative_data = b""  # To keep track of cumulative data for checksum calculation

            for append, chunk in enumerate(chunks, start=1):
                cumulative_data += chunk  # Append current chunk to cumulative data
                chunk_checksum = crc16(cumulative_data)  # Calculate checksum of cumulative data

                update_data.append({
                    "contents": chunk.decode("utf-8"),  # Chunks are Base64 encoded bytes, so decode to str
                    "FileType": relative_path.replace("\\", "/"),
                    "Checksum": chunk_checksum,  # Use cumulative checksum
                    "Binary": True,  # Always treated as binary
                    "append": append,
                    "Version": version,
                    "GameName": "11",
                })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(update_data, f, indent=4)

    print(f"Update file '{output_file}' generated successfully.")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build update JSON file for the board.")
    parser.add_argument("--build-dir", default=BUILD_DIR, help="Path to the build directory.")
    parser.add_argument("--source-dir", default=SOURCE_DIR, help="Path to the source directory.")
    parser.add_argument("--output", default=OUTPUT_FILE, help="Path to the output JSON file.")
    parser.add_argument("--version", help="Version string (e.g., '0.3.0'). If omitted, extracted from SharedState.py.")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Maximum chunk size for file splitting (in bytes).")
    args = parser.parse_args()

    # Extract version if not provided
    def extract_version(source_dir: str) -> str:
        """Extract version from SharedState.py."""
        shared_state_path = Path(source_dir) / "SharedState.py"
        if not shared_state_path.exists():
            raise FileNotFoundError(f"SharedState.py not found at {shared_state_path}")

        with open(shared_state_path, "r") as f:
            for line in f:
                if "WarpedVersion" in line:
                    return line.split("=")[1].strip().strip('"')

        raise ValueError("WarpedVersion not found in SharedState.py")

    version = args.version or extract_version(args.source_dir)
    build_update_json(args.build_dir, args.output, version, args.chunk_size)
