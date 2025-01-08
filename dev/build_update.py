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

    Then add at the top of the final file a single-line JSON object that indicates
    the byte start and length of each section (metadata, files, signature), as
    divided by the \n----\n separators.
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

    # a) The metadata in JSON
    meta_str = json.dumps(meta_data, indent=2)

    # b) Prepare the content before signature as one big string
    #    We'll insert a \n----\n as the section delimiter
    #    Section 1: metadata
    #    Section 2: removal_line + all file lines
    section_1 = meta_str
    section_2_list = [removal_line] + file_lines
    section_2 = "\n".join(section_2_list)

    content_before_signature = section_1 + "\n----\n" + section_2

    # Sign that content
    sha256_hex, signature_b64 = sign_data(content_before_signature.encode("utf-8"), private_key_path)

    # c) Prepare the signature block as its own section
    #    (with the leading ---- delimiter so it's recognized as a new section)
    signature_obj = {
        "sha256": sha256_hex,
        "signature": signature_b64
    }
    section_3 = json.dumps(signature_obj)
    full_body = content_before_signature + "\n----\n" + section_3 + "\n"

    # Now determine the byte offsets of each section within full_body
    # We'll search for the two \n----\n delimiters
    #   Section layout in full_body:
    #   [metadata text]
    #   \n----\n
    #   [files text]
    #   \n----\n
    #   [signature text]\n
    #
    # The signature text includes a trailing newline.  
    # We want: 
    #   metadata:   start=0               length= up to (but not including) \n----\n
    #   files:      start= (delim1_end)   length= up to (but not including) next \n----\n
    #   signature:  start= (delim2_end)   length= the remainder of the file
    #
    # The final output will get a new line at the top, but we measure offsets from the beginning
    # of that final file, so we have to add the length of that new offsets line + newline
    # if we want correct absolute offsets. Let’s do it that way: first compute raw offsets
    # in full_body, then we’ll shift them by the length of the offsets line once we know it.

    delim1_pos = full_body.index("\n----\n")
    delim2_pos = full_body.index("\n----\n", delim1_pos + 1)

    # The metadata section goes [0 : delim1_pos]
    metadata_start_raw = 0
    metadata_length = delim1_pos  # everything up to that delimiter

    # The files section starts right after delim1_pos + len("\n----\n")
    files_start_raw = delim1_pos + len("\n----\n")
    files_length = delim2_pos - files_start_raw

    # The signature section starts right after delim2_pos + len("\n----\n")
    signature_start_raw = delim2_pos + len("\n----\n")
    signature_length = len(full_body) - signature_start_raw

    # Offsets after we prepend the offsets line:
    # We'll build the offsets line JSON with placeholders for now, measure its length,
    # then add that to the raw offsets. We only need to do it once.
    offsets_stub = {"metadata": {"start": 0, "length": metadata_length},
                    "files": {"start": 0, "length": files_length},
                    "signature": {"start": 0, "length": signature_length}}
    # Measure the JSON line if we were to put real offsets in
    # We'll guess maximum length; for safety, just build the final now:
    offsets_test_line = json.dumps(offsets_stub, separators=(',',':'))
    # We'll add 1 for the newline
    stub_line_len = len(offsets_test_line) + 1

    # Now shift all raw starts by stub_line_len
    metadata_start = metadata_start_raw + stub_line_len
    files_start = files_start_raw + stub_line_len
    signature_start = signature_start_raw + stub_line_len

    # Build the actual offsets dictionary
    offsets = {
        "metadata": {"start": metadata_start, "length": metadata_length},
        "files": {"start": files_start, "length": files_length},
        "signature": {"start": signature_start, "length": signature_length},
    }
    offsets_line = json.dumps(offsets, separators=(',', ':'))

    # Final output = offsets line + newline + the full body
    final_output = offsets_line + "\n" + full_body

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
