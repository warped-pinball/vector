#!/usr/bin/env python3

import os
import json
import base64
import hashlib
from pathlib import Path
from typing import Optional, Union
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
import argparse

BUILD_DIR = "build"
SOURCE_DIR = "src"
OUTPUT_FILE = "update.json"

def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> str:
    """
    Calculate a single CRC16-CCITT (0x1021) in hex-string form (uppercase).
    """
    for byte in data:
        crc ^= (byte << 8)
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

def build_remove_extra_files_code(build_dir: str) -> bytes:
    """
    Build a Micropython script that removes any file not present in 'build_dir'.
    Return it as raw bytes ready for base64 encoding.
    """
    known_files = []
    for root, _, files in os.walk(build_dir):
        for file_name in files:
            file_path = Path(root) / file_name
            relative_path = os.path.relpath(file_path, build_dir)
            known_files.append("/" + relative_path.replace("\\","/"))

    removal_code = "\n".join([
        "import os",
        "",
        f"known_files={known_files}",
        "def rm_walk(top):",
        "    try:",
        "        entries = os.listdir(top)",
        "    except OSError:",
        "        return",
        "    for entry in entries:",
        "        path=top + '/' + entry if top != '/' else '/' + entry",
        "        try:",
        "            if os.stat(path)[0] & 0x4000:  # directory check",
        "                rm_walk(path)",
        "            elif path not in known_files:",
        "                print('Removing', path)",
        "                os.remove(path)",
        "        except OSError:",
        "            continue",
        "rm_walk('/')"
    ])
    return removal_code.encode("utf-8")

def make_file_line(
    file_path: str,
    file_contents: bytes,
    custom_log: Optional[str] = None,
    execute: bool = False
) -> str:
    """
    Create a single line representing one file’s update entry:
        filename + jsonDictionary + base64EncodedFileContents

    Example line:
        some_file.py{"checksum":"ABCD","bytes":1234,"log":"Uploading some_file.py"}c29tZSBiYXNlNjQgZGF0YQ==
    """
    checksum = crc16_ccitt(file_contents)
    file_size = len(file_contents)
    b64_data = base64.b64encode(file_contents).decode("utf-8")

    file_meta = {
        "checksum": checksum,
        "bytes": file_size,
        "log": custom_log if custom_log else f"Uploading {file_path}",
    }
    if execute:
        file_meta["execute"] = True

    meta_json = json.dumps(file_meta, separators=(',', ':'))
    return f"{file_path}{meta_json}{b64_data}"

def sign_data(data: bytes, private_key_path: Optional[str]) -> (str, str):
    """
    Compute the SHA256 over 'data'.
    If private_key_path is provided, sign that hash using the private key.
    Returns (sha256_hex, signature_b64).
    """
    sha256_digest = hashlib.sha256(data).digest()
    sha256_hex = hashlib.sha256(data).hexdigest()

    if private_key_path:
        with open(private_key_path, 'rb') as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None
            )
        signature = private_key.sign(
            sha256_digest,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        return (sha256_hex, signature_b64)
    else:
        return (sha256_hex, "NOT_ENCRYPTED")

def build_update_file(
    build_dir: str,
    output_file: str,
    version: str,
    private_key_path: Optional[str],
):
    """
    1) Create one JSON line of metadata at the top.
    2) Then a line per file in 'build_dir' (plus remove_extra_files.py).
    3) Finally one line containing {"sha256": "...", "signature": "..."} at the bottom.

    No 'section' headers or lengths. The user can just read the last line as the signature.
    """

    # 1) Build top-level metadata as a single line
    meta_data = {
        "update_file_format": "1.0",
        "supported_hardware": ["vector_v4", "vector_v5"],
        "supported_software_versions": ["0.3.0"],
        "micropython_versions": ["1.23.0.preview"],
        "version": version
    }
    metadata_line = json.dumps(meta_data, separators=(',', ':'))

    # 2) Build lines for files
    # 2a) remove_extra_files.py
    removal_bytes = build_remove_extra_files_code(build_dir)
    removal_line = make_file_line(
        "remove_extra_files.py",
        removal_bytes,
        custom_log="Removing extra files",
        execute=True
    )
    file_lines = [removal_line]

    # 2b) everything else in build_dir
    for root, _, files in os.walk(build_dir):
        for file_name in files:
            file_path = Path(root) / file_name
            relative_path = os.path.relpath(file_path, build_dir).replace("\\", "/")
            if relative_path == "remove_extra_files.py":
                continue
            contents = get_file_contents(file_path)
            file_lines.append(
                make_file_line(
                    relative_path,
                    contents,
                    custom_log=f"Uploading {relative_path}"
                )
            )

    # 3) Sign everything except the signature line:
    # Concatenate metadata_line plus all file_lines with newlines in between.
    update_body = "\n".join([metadata_line] + file_lines)
    sha256_hex, signature_b64 = sign_data(update_body.encode("utf-8"), private_key_path)

    signature_line = json.dumps({
        "sha256": sha256_hex,
        "signature": signature_b64
    }, separators=(',', ':'))

    # Final output: top line is metadata, then all file lines, then signature line
    final_output = "\n".join([metadata_line] + file_lines + [signature_line]) + "\n"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(final_output)

def extract_version(source_dir: str) -> str:
    """
    If version is not provided, attempt to extract it from SharedState.py
    by searching for 'WarpedVersion'.
    """
    shared_state_path = Path(source_dir) / "SharedState.py"
    if not shared_state_path.exists():
        raise FileNotFoundError(f"SharedState.py not found at {shared_state_path}")

    with open(shared_state_path, "r", encoding="utf-8") as f:
        for line in f:
            if "WarpedVersion" in line:
                return line.split("=")[1].strip().strip('"')
    raise ValueError("WarpedVersion not found in SharedState.py")

def main():
    parser = argparse.ArgumentParser(description="Build single-line-per-file update file with minimal overhead.")
    parser.add_argument("--build-dir", default=BUILD_DIR, help="Path to the build directory.")
    parser.add_argument("--source-dir", default=SOURCE_DIR, help="Path to the source directory.")
    parser.add_argument("--output", default=OUTPUT_FILE, help="Path to the output file.")
    parser.add_argument("--version", help="Version string (e.g., '0.3.0'). If omitted, extracted from SharedState.py.")
    parser.add_argument("--private-key", help="Path to a PEM-encoded private key for signing.")
    args = parser.parse_args()

    # If no version is provided, extract from SharedState.py
    final_version = args.version or extract_version(args.source_dir)

    build_update_file(
        build_dir=args.build_dir,
        output_file=args.output,
        version=final_version,
        private_key_path=args.private_key
    )

if __name__ == "__main__":
    main()
