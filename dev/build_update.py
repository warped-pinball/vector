#!/usr/bin/env python3

import os
import json
import binascii
from pathlib import Path
from typing import Union

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

def build_extra_file_removal_step(build_dir: str, chunk_size: int = 1024) -> list[dict]:
    "build a step to remove any file that is not in the build directory"
    known_files = []
    for root, _, files in os.walk(build_dir):
        for file_name in files:
            file_path = Path(root) / file_name
            relative_path = os.path.relpath(file_path, build_dir)
            known_files.append('/' + relative_path)

    # micropython code to walk the filesystem and remove any file that is not in the known_files list
    # this code will be executed by the board at the start of the update process
    removal_code = '\n'.join(
        [
            "import os",
            "",
            "known_files={}".format(known_files),
            "def rm_walk(top):",
            "    try:",
            "        entries = os.listdir(top)",
            "    except OSError:",
            "        return",
            "    for entry in entries:",
            '        path=top + "/" + entry if top != "/" else "/" + entry',
            "        try:",
                        # 0x4000 is the S_IFDIR flag indicating a directory
            "            if os.stat(path)[0] & 0x4000:",
            "                rm_walk(path)",
            "            elif path not in known_files:",
            "                print('Removing', path)",
            "                os.remove(path)",
            "        except OSError:",
            "            continue",
            "rm_walk('/')"            
        ]
    )

    # make removal code into bytes
    removal_code = removal_code.encode("utf-8")

    return make_file_entries("remove_extra_files.py", removal_code, chunk_size, execute=True, custom_log="Removing extra files")

def make_file_entries(file_path: str, file_contents: bytes, chunk_size: int, execute: bool=False, custom_log:Union[str, None]=None) -> list[dict]:
    """Create a file entry for the update JSON."""
    
    # Split into chunks
    chunks = split_into_chunks(file_contents, chunk_size)

    # encode the chunks
    encoded_chunks = [binascii.b2a_base64(chunk)[:-1] for chunk in chunks]

    # Calculate cumulative checksums of encoded chunks
    cumulative_checksum_data = b""
    previous_chunk_checksum = 0xFFFF
    checksums = []
    for chunk in encoded_chunks:
        chunk_checksum = crc16_ccitt(chunk, previous_chunk_checksum)
        previous_chunk_checksum = int(chunk_checksum, 16)
        checksums.append(chunk_checksum)
        cumulative_checksum_data += chunk
    
    parts = [
        {
            "path": file_path,
            "checksum": checksum,
            "data": chunk.decode("utf-8"),
            # add the part number if there are more than one
            "part": part_number if len(chunks) > 1 else None,
            "final_bytes": len(file_contents),
            "log": custom_log if custom_log else f"Uploading {file_path} (part {part_number} of {len(chunks)})",
            # add the execute flag (false for all but the last part) if the file should be executed
            "execute": bool(execute and part_number == len(chunks)) if execute else None
        }
        for part_number, (chunk, checksum) in enumerate(zip(encoded_chunks, checksums), start=1)
    ]

    # remove keys that are null/None
    for part in parts:
        for key in list(part.keys()):
            if part[key] is None:
                del part[key]
    
    return parts
    

def build_update_json(build_dir: str, output_file: str, version: str, chunk_size: int):
    update_data = {
        "update_file_format": "1.0",
        "supported_hardware": ["vector_v1", "vector_v2", "vector_v3", "vector_v4", "vector_v5"],
        "supported_software_versions": ["0.3.0"],
        "micropython_versions": ["1.23.0"],
        "version": version,
        "chunk_size": chunk_size,
        "files": build_extra_file_removal_step(build_dir)
    }

    for root, _, files in os.walk(build_dir):
        for file_name in files:
            file_path = Path(root) / file_name
            relative_path = os.path.relpath(file_path, build_dir)
            contents = get_file_contents(file_path)
            update_data["files"] += make_file_entries(relative_path, contents, chunk_size)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(update_data, f, indent=2)

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


#TODO first step of update should be to rewrite boot or main to hold reset pin and go to a transparent mode / safe state
