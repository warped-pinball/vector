#!/usr/bin/env python3

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

BUILD_DIR = "build"
SOURCE_DIR = "src"
OUTPUT_FILE = "update.json"


def all_combos(pico_list, micropython_list):
    return [{"pico": pico, "micropython": mp} for pico in pico_list for mp in micropython_list]


compatible_configurations = {
    "sys11": all_combos(["1w"], ["1.24.1", "1.23.0.preview"]) + all_combos(["2w"], ["1.25.0"]),
    "wpc": all_combos(["2w"], ["1.25.0", "1.26.0.preview"]),
    "em": all_combos(["2w"], ["1.26.0.preview"]),
    "data_east": all_combos(["2w"], ["1.25.0"]),
    "whitestar": all_combos(["2w"], ["1.25.0"]),
}


def resolve_build_dir(build_dir: Optional[str], target_hardware: str) -> str:
    """Return the build directory for *target_hardware*.

    ``build_dir`` may point to the root ``build`` directory. In that case the
    hardware-specific subdirectory is appended automatically.
    """

    path = Path(build_dir) if build_dir else Path(BUILD_DIR) / target_hardware
    if path.name == BUILD_DIR:
        path = path / target_hardware
    return str(path)


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> str:
    """
    Calculate a single CRC16-CCITT (0x1021) in hex-string form (uppercase).
    """
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


def build_update_metadata(target_hardware: str, version: str) -> dict:
    hardware_metadata = compatible_configurations.get(target_hardware, {})
    if not hardware_metadata:
        raise ValueError(f"Unsupported target hardware: {target_hardware}")

    # combine the default metadata with hardware-specific metadata
    meta_data = {
        "update_file_format": "1.0",
        "downgradable_to": ["1.0.0"],
        "version": version,
        # This is the list of all hardware that was sold with software that checks for compatibility this way
        # It's now kept only to ensure those boards can update directly to the latest version
        "supported_hardware": ["vector_v4", "vector_v5", "wpc_vector_v1"],
        # We simply list all the micropython versions that are supported by the target hardware and not specific combinations of hardware/micropython
        # Since this is only checked by old versions of the update code the real "check" is done in the confirm_compatibility.py script
        "micropython_versions": [combo["micropython"] for combo in hardware_metadata],
    }

    return json.dumps(meta_data, separators=(",", ":"))


def make_file_line(
    file_path: str,
    file_contents: bytes,
    custom_log: Optional[str] = None,
    execute: bool = False,
) -> str:
    """
    Create a single line representing one file's update entry:
        filename + jsonDictionary + base64EncodedFileContents

    Example line:
        some_file.py{"checksum":"ABCD","bytes":1234,"log":"Uploading file"}c29tZSB
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

    meta_json = json.dumps(file_meta, separators=(",", ":"))
    return f"{file_path}{meta_json}{b64_data}"


def build_confirm_compatibility_code(target_hardware: str) -> bytes:
    """
    Build a Micropython script that checks for compatible hardware and micropython versions.
    Return it as raw bytes ready for base64 encoding.
    """
    code = "\n".join(
        [
            "from sys import implementation",
            "pico_strs = {",
            "   'Raspberry Pi Pico with RP2040': '1w',",
            "   'Raspberry Pi Pico 2 W with RP2350': '2w'",
            "},",
            "pico_version = pico_strs[implementation._machine]" "micropython_version = '.'.join([str(i) for i in implementation.version])" "try:",
            "    from systemConfig import vectorSystem",
            "except:",
            "    vectorSystem = None",
            # define all valid hardware/micropython/system combinations
            "pico_and_micropython_pairs = [",
        ]
        + [f"    ({pico!r}, {micropython!r})" for pico, micropython in compatible_configurations.get(target_hardware, [])]
        + [
            "]",
            "valid = False",
            "for pico, micropython in pico_and_micropython_pairs:",
            "    if pico_version != pico:",
            "        continue",
            "    if micropython_version != micropython:",
            "        continue",
            "    if vectorSystem is None or vectorSystem == {target_hardware!r}:",
            "        valid = True",
            "        break",
            "if not valid:",
            "   raise RuntimeError(f'Hardware / Micropython version / System combination not supported for this update: {pico_version} / {micropython_version} / {vectorSystem}')",
        ]
    )
    return make_file_line(
        "confirm_compatibility.py",
        code.encode("utf-8"),
        custom_log="Checking update compatibility",
    )


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
            known_files.append("/" + relative_path.replace("\\", "/"))

    removal_code = "\n".join(
        [
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
            "rm_walk('/')",
        ]
    )
    return make_file_line(
        "remove_extra_files.py",
        removal_code.encode("utf-8"),
        custom_log="Checking update compatibility",
    )


def sign_data(data: bytes, private_key_path: Optional[str]) -> (str, str):
    """
    Compute the SHA256 over 'data'.
    If private_key_path is provided, sign that hash using the private key.
    Returns (sha256_hex, signature_b64).
    """
    sha256_digest = hashlib.sha256(data).digest()
    sha256_hex = hashlib.sha256(data).hexdigest()

    if private_key_path:
        with open(private_key_path, "rb") as key_file:
            private_key = serialization.load_pem_private_key(key_file.read(), password=None)
        signature = private_key.sign(sha256_digest, padding.PKCS1v15(), hashes.SHA256())
        signature_b64 = base64.b64encode(signature).decode("utf-8")
        return (sha256_hex, signature_b64)
    else:
        return (sha256_hex, "NOT_ENCRYPTED")


def build_update_file(
    build_dir: str,
    output_file: str,
    version: str,
    private_key_path: Optional[str],
    target_hardware: str = "sys11",
):
    """
    1) Create one JSON line of metadata at the top.
    2) Then a line per file in 'build_dir' (plus remove_extra_files.py).
    3) Finally one line containing {"sha256": "...", "signature": "..."} at the bottom.
    """

    build_dir_path = Path(build_dir)

    # confirm that the build_dir exists and is a directory that does not contain hardware-specific subdirectories
    subdirs = {p.name for p in build_dir_path.iterdir() if p.is_dir()}
    if any(name in compatible_configurations for name in subdirs):
        raise ValueError("build_dir must point to a hardware-specific subdirectory like 'build/sys11'")

    file_lines = [build_update_metadata(target_hardware, version), build_confirm_compatibility_code(target_hardware), build_remove_extra_files_code(build_dir)]

    # 2b) everything else in build_dir
    for root, _, files in os.walk(build_dir):
        for file_name in files:
            file_path = Path(root) / file_name
            relative_path = os.path.relpath(file_path, build_dir).replace("\\", "/")
            if relative_path == "remove_extra_files.py":
                continue
            contents = get_file_contents(file_path)
            file_lines.append(make_file_line(relative_path, contents, custom_log=f"Uploading {relative_path}"))

    # 3) Sign everything except the signature line:
    # Concatenate metadata_line plus all file_lines with newlines in between.
    update_body = "\n".join(file_lines)
    sha256_hex, signature_b64 = sign_data(update_body.encode("utf-8"), private_key_path)

    signature_line = json.dumps({"sha256": sha256_hex, "signature": signature_b64}, separators=(",", ":"))

    # Final output: top line is metadata, then all file lines, then signature line
    final_output = "\n".join(file_lines + [signature_line]) + "\n"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(final_output)


def main():
    parser = argparse.ArgumentParser(description="Build single-line-per-file update file with minimal overhead.")
    parser.add_argument(
        "--build-dir",
        help="Path to the build directory (defaults to build/<target_hardware>).",
    )
    parser.add_argument("--output", default=OUTPUT_FILE, help="Path to the output file.")
    parser.add_argument("--version", help="Version string (e.g., '0.3.0')", required=True)
    parser.add_argument(
        "--target_hardware",
        default="sys11",
        help="Target system for the update (e.g., data_east, sys11, whitestar, wpc, em, etc.)",
    )
    parser.add_argument("--private-key", help="Path to a PEM-encoded private key for signing.")
    args = parser.parse_args()

    build_dir = resolve_build_dir(args.build_dir, args.target_hardware)
    build_update_file(
        build_dir=build_dir,
        output_file=args.output,
        version=args.version,
        private_key_path=args.private_key,
        target_hardware=args.target_hardware,
    )


if __name__ == "__main__":
    main()
