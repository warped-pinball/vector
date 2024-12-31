import os
import json
from pathlib import Path

BUILD_DIR = "build"
OUTPUT_FILE = "update.json"


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


def build_runme_script(file_list):
    """Generate RunMe.py to handle .mpy renaming on the board."""
    rename_script = [
        "import os",
        "from logger import logger_instance",
        "Log = logger_instance",
        "",
        "def rename_files():",
    ]
    for file in file_list:
        if file.endswith(".mpy"):
            original = file
            renamed = file[:-4]  # Remove .mpy
            rename_script.append(f"    try:")
            rename_script.append(f"        os.rename('{original}', '{renamed}')")
            rename_script.append(f"        Log.log('Renamed {original} to {renamed}')")
            rename_script.append(f"    except Exception as e:")
            rename_script.append(f"        Log.log('Failed to rename {original}: {e}')")
    rename_script.append("if __name__ == '__main__':")
    rename_script.append("    rename_files()")
    return "\n".join(rename_script)


def build_update_json(build_dir: str, output_file: str):
    update_data = []
    file_list = []

    for root, _, files in os.walk(build_dir):
        for file_name in files:
            file_path = Path(root) / file_name
            relative_path = os.path.relpath(file_path, build_dir)

            contents = get_file_contents(file_path)
            checksum = crc16(contents)

            file_type = relative_path.replace("\\", "/")

            # Convert unsupported files to .mpy
            if not (file_name.endswith(".py") or file_name.endswith(".json")):
                file_type += ".mpy"
                contents = contents.decode("latin1")  # Encode binary as latin1
            else:
                contents = contents.decode("utf-8")

            update_data.append({
                "contents": contents,
                "FileType": file_type,
                "Checksum": checksum,
                "Version": "00.20",
                "GameName": "11",
            })

            file_list.append(file_type)

    # Add RunMe.py for renaming
    runme_script = build_runme_script(file_list)
    runme_checksum = crc16(runme_script.encode("utf-8"))
    update_data.append({
        "contents": runme_script,
        "FileType": "RunMe.py",
        "Checksum": runme_checksum,
        "Version": "00.20",
        "GameName": "11",
    })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(update_data, f, indent=4)

    print(f"Update file '{output_file}' generated successfully.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build update JSON file for the board.")
    parser.add_argument("--build-dir", default=BUILD_DIR, help="Path to the build directory.")
    parser.add_argument("--output", default=OUTPUT_FILE, help="Path to the output JSON file.")
    args = parser.parse_args()

    build_update_json(args.build_dir, args.output)