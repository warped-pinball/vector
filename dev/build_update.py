#!/usr/bin/env python3

import os
import json
import base64
from pathlib import Path
import zlib

BUILD_DIR = "build"
SOURCE_DIR = "src"
OUTPUT_FILE = "update.json"
DEFAULT_CHUNK_SIZE = 1024

def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return "{:04X}".format(crc)

def get_file_contents(file_path: str) -> bytes:
    with open(file_path, "rb") as f:
        return f.read()

def split_into_chunks(data: bytes, chunk_size: int) -> list[bytes]:
    """Split data into chunks of a given size."""
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

def build_update_json(build_dir: str, output_file: str, version: str, chunk_size: int):
    update_data = {
        "update_file_format": "1.0",
        "supported_hardware": ["vector_v1", "vector_v2", "vector_v3", "vector_v4", "vector_v5"],
        "supported_software_versions": ["0.3.0"],
        "micropython_versions": ["1.23.0"],
        "version": version,
        "full_checksum": "",
        "files": []
    }

    cumulative_checksum_data = b""

    for root, _, files in os.walk(build_dir):
        for file_name in files:
            file_path = Path(root) / file_name
            relative_path = os.path.relpath(file_path, build_dir)

            contents = get_file_contents(file_path)

            # Split into chunks
            chunks = split_into_chunks(contents, chunk_size)

            # cumulative_data = b""
            total_parts = len(chunks)

            previous_chunk_checksum = 0xFFFF
            for part_number, chunk in enumerate(chunks, start=1):
                encoded_chunk = base64.b64encode(chunk)
                chunk_checksum = crc16_ccitt(encoded_chunk, previous_chunk_checksum)
                previous_chunk_checksum = int(chunk_checksum, 16)
                log_message = f"Uploading {relative_path} (part {part_number} of {total_parts})"

                file_entry = {
                    "path": relative_path.replace("\\", "/"),
                    "checksum": chunk_checksum,
                    "data": encoded_chunk.decode("utf-8"),
                    "log": log_message
                }

                if total_parts > 1:
                    file_entry["part_number"] = part_number
                    file_entry["total_parts"] = total_parts

                update_data["files"].append(file_entry)


            cumulative_checksum_data += encoded_chunk

    update_data["full_checksum"] = crc16_ccitt(cumulative_checksum_data)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(update_data, f, indent=2)

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
