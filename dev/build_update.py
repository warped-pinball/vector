#!/usr/bin/env python3

import os
import json
import base64
import binascii
import hashlib
from pathlib import Path
from typing import Optional, Union
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, utils
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
            # store them with a leading slash so the final board’s file structure matches
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
    custom_log: Union[str, None] = None,
    execute: bool = False
) -> str:
    """
    Create a single line representing one file’s update entry.
    Format:
        filename + jsonDictionary + base64EncodedFileContents
    Example:
        some_file.py{"checksum":"ABCD","bytes":1234,"log":"Uploading some_file.py"}c29tZSBiYXNlNjQgZGF0YQ==
    """
    checksum = crc16_ccitt(file_contents)
    file_size = len(file_contents)
    # Base64-encode the entire file contents in a single line
    b64_data = base64.b64encode(file_contents).decode("utf-8")

    # Build up the metadata for this file
    file_meta = {
        "checksum": checksum,
        "bytes": file_size,
        "log": custom_log if custom_log else f"Uploading {file_path}",
    }
    if execute:
        file_meta["execute"] = True

    meta_json = json.dumps(file_meta, separators=(',', ':'))
    line = f"{file_path}{meta_json}{b64_data}"
    return line

def sign_data(data: bytes, private_key_path: Optional[str]) -> (str, str):
    """
    Compute the SHA256 over 'data' (everything before the signature block).
    If private_key_path is provided, load the private key and sign that hash.

    Returns:
      (sha256_hex, signature_text)
       - sha256_hex: hex digest of the data
       - signature_text: base64-encoded RSA signature, or 'NOT_ENCRYPTED'

    About the RSA signature call:
      - We use RSA PKCS#1 v1.5 padding (padding.PKCS1v15()).
      - This is the standard older padding scheme for RSA. 
        It's still commonly used for signing (though PSS is considered more secure). 
      - utils.Prehashed(hashes.SHA256()) means we're telling cryptography we already hashed 
        the data (the 'data' parameter is the digest, not the original plaintext). 
        So we pass the raw digest to private_key.sign() along with the chosen padding/hashing scheme.
    """
    sha256_digest = hashlib.sha256(data).digest()
    sha256_hex = hashlib.sha256(data).hexdigest()

    if private_key_path:
        # Load the private key
        with open(private_key_path, 'rb') as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None
            )
        # Sign the raw digest with RSA PKCS#1 v1.5 using SHA256
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
    public_key_path: Optional[str] = None
):
    """
    Build the new "single-line-per-file" output file with:
      1) JSON meta block
      2) Separator line (----)
      3) One line per file in build_dir (including remove_extra_files.py)
      4) Another separator line (----)
      5) A final signature block containing: sha256=... and signature=...
         (the signature is over everything above it).

    If public_key_path is provided, we copy that public key into the build directory
    so that it will be included on the board as well. (Named 'public_key.pem'.)
    """
    # If a public key is provided, copy it to the build directory so it gets included.
    # Name it consistently, e.g. "public_key.pem".
    if public_key_path:
        dest = Path(build_dir) / "public_key.pem"
        with open(public_key_path, "rb") as in_f, open(dest, "wb") as out_f:
            out_f.write(in_f.read())

    # 1) Create the top-level metadata object
    meta_data = {
        "update_file_format": "1.0",
        "supported_hardware": ["vector_v4","vector_v5"],
        "supported_software_versions": ["0.3.0"],
        "micropython_versions": ["1.23.0.preview"],
        "version": version
    }

    # 2) Generate the remove_extra_files.py "file line"
    removal_bytes = build_remove_extra_files_code(build_dir)
    removal_line = make_file_line(
        "remove_extra_files.py",
        removal_bytes,
        custom_log="Removing extra files",
        execute=True
    )

    # 3) Gather all files in build_dir, create lines for each
    file_lines = []
    for root, _, files in os.walk(build_dir):
        for file_name in files:
            file_path = Path(root) / file_name
            relative_path = os.path.relpath(file_path, build_dir).replace("\\","/")
            # skip physically existing remove_extra_files.py to avoid duplication
            if relative_path == "remove_extra_files.py":
                continue
            contents = get_file_contents(file_path)
            line = make_file_line(
                relative_path,
                contents,
                custom_log=f"Uploading {relative_path}",
                execute=False
            )
            file_lines.append(line)

    # Combine everything (except the signature) into one text block.
    lines_to_write = []

    # a) The metadata in pretty JSON
    meta_str = json.dumps(meta_data, indent=2)
    lines_to_write.append(meta_str)

    # b) A separator
    lines_to_write.append("----")

    # c) The "remove_extra_files.py" line
    lines_to_write.append(removal_line)

    # d) Each file line
    lines_to_write.extend(file_lines)

    # Build one big string from these parts
    # each part in lines_to_write is its own line
    content_before_signature = "\n".join(lines_to_write)

    # Now sign that content
    sha256_hex, signature_b64 = sign_data(content_before_signature.encode("utf-8"), private_key_path)

    # e) Final signature block with the same separator
    signature_block = [
        "----",
        f"sha256={sha256_hex}",
        f"signature={signature_b64}"
    ]
    signature_section = "\n".join(signature_block)

    # Final output
    final_output = content_before_signature + "\n" + signature_section + "\n"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(final_output)

def extract_version(source_dir: str) -> str:
    """Extract version from SharedState.py."""
    shared_state_path = Path(source_dir) / "SharedState.py"
    if not shared_state_path.exists():
        raise FileNotFoundError(f"SharedState.py not found at {shared_state_path}")

    with open(shared_state_path, "r", encoding="utf-8") as f:
        for line in f:
            if "WarpedVersion" in line:
                return line.split("=")[1].strip().strip('"')
    raise ValueError("WarpedVersion not found in SharedState.py")

def main():
    parser = argparse.ArgumentParser(description="Build single-line-per-file update file for the board, with optional signing.")
    parser.add_argument("--build-dir", default=BUILD_DIR, help="Path to the build directory.")
    parser.add_argument("--source-dir", default=SOURCE_DIR, help="Path to the source directory.")
    parser.add_argument("--output", default=OUTPUT_FILE, help="Path to the output file.")
    parser.add_argument("--version", help="Version string (e.g., '0.3.0'). If omitted, extracted from SharedState.py.")
    parser.add_argument("--private-key", help="Path to a PEM-encoded private key for signing.")
    parser.add_argument("--public-key", help="Path to the PEM-encoded public key to include in the build output.")
    args = parser.parse_args()

    # If version is not provided, try to extract from SharedState.py
    final_version = args.version or extract_version(args.source_dir)

    build_update_file(
        args.build_dir,
        args.output,
        final_version,
        args.private_key,
        args.public_key
    )

if __name__ == "__main__":
    main()
