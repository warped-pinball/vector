"""
file operations generally for the admin page
V12/9/2024 support for software download
"""
import gc
import json

import SPI_DataStore as DataStore
from logger import logger_instance

Log = logger_instance


# Logic for importing scores supporting any format changes
def upgrade_score_export_format(data):
    version = get_score_export_version(data)
    # Upgrade file through all version upgrade functions
    while version in score_version_upgrades:
        data = score_version_upgrades[version](data)
        if "version" not in data or data["version"] == version:
            # Version did not increment, or some other error.
            raise ValueError("Failed to upgrade score import format!")
        version = data["version"]
    return data


def get_score_export_version(data):
    if "version" in data:
        return data["version"]
    return 0


# Version "0" was "classic score" format, before we versioned it.
def score_export_0_to_1(data):
    output = {"version": 1, "scores": {}}
    # Convert to nicer format, with version number
    for row in data:
        output["scores"][row["FileType"]] = row["contents"]
    return output


# If we ever change the format again, we can use the below dictionary and functions named as so to update the format from older exports so they'll continue to work.
# def score_export_1_to_2(data):

current_score_version = 1
score_version_upgrades = {0: score_export_0_to_1}


def _get_scores_no_zeros(list):
    result = []
    for i in range(DataStore.memory_map["leaders"]["count"]):
        row = DataStore.read_record("leaders", i)
        if row["score"] > 0:
            result.append(row)
    return result


def download_scores():
    data = {"version": current_score_version, "scores": {"leaders": _get_scores_no_zeros("leaders"), "tournament": _get_scores_no_zeros("tournament")}}
    return json.dumps(data)


def import_scores(data):
    from ScoreTrack import bulk_import_scores

    # Upgrade format if needed
    data = upgrade_score_export_format(data)
    if "scores" in data:
        if "leaders" in data["scores"]:
            bulk_import_scores(data["scores"]["leaders"], "leaders")
        if "tournament" in data["scores"]:
            bulk_import_scores(data["scores"]["tournament"], "tournament")
    return True


# download the list of players
def download_names(request):
    gc.collect()
    print("download names - - - ")
    try:
        # Collect player names data
        names_data = [DataStore.read_record("names", i) for i in range(DataStore.memory_map["names"]["count"])]

        response_body = [{"FileType": "names", "contents": names_data}]
        # Prepare the final response
        response = {
            "headers": {
                "Content-Type": "application/json",
                "Content-Disposition": "attachment; filename=names.json",
                "Connection": "close",
            },
            "body": json.dumps(response_body),
        }
        return json.dumps(response)

    except Exception as e:
        print(f"Error generating download: {e}")
        return json.dumps(
            {
                "headers": {"Content-Type": "application/json", "Connection": "close"},
                "body": json.dumps({"error": "An error occurred while generating the download."}),
            }
        )


def download_log():
    try:
        # Prepare the response headers
        headers = {
            "Content-Type": "text/plain",
            "Content-Disposition": "attachment; filename=log.txt",
            "Connection": "close",
        }

        # Generator function to stream
        def log_stream_generator():
            for line in logger_instance.get_logs_stream():
                yield line

        return log_stream_generator(), 200, headers

    except Exception as e:
        print(f"Error generating download: {e}")
        return "An error occurred while generating the download.", 500


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
    crc_value = crc16_ccitt(data)
    return "{:04X}".format(crc_value)


# Base64 decoding function for MicroPython
def base64_decode(data):
    """Decode a Base64 encoded string into bytes."""
    import ubinascii

    return ubinascii.a2b_base64(data)


# TODO this is unused, we should probably remove it
def set_file_size(path, num_bytes, preserve_to_byte=0):
    # makes a file of a certain size with minimal edits
    # used in updating files
    from os import remove

    # ensure file is of correct size
    # We make sure the file is the correct total size even if we wont be writing to the whole file yet
    # This is hopefully reduce fragmentation on the file system and it should be about 70ms faster per request to write to a file that is already the correct size
    file_size = None
    try:
        # open for reading and writing, raise an exception if the file does not exist
        with open(path, "rb+") as f:
            f.seek(0, 2)
            file_size = f.tell()

            # if it's smaller than the final size, pad it with null bytes
            if file_size < num_bytes:
                print(f"Padding file {path} with {num_bytes - file_size} null bytes")
                f.write(b"\x00" * (num_bytes - file_size))
                file_size = num_bytes

    # catch ENOENT exception
    except OSError:
        # if the file does not exist, create it with the correct size
        with open(path, "w") as f:
            print(f"Creating file {path} with {num_bytes} null bytes")
            f.write(b"\x00" * num_bytes)
            file_size = num_bytes
    except Exception as e:
        raise e

    # if the file exists, but is too large
    if file_size > num_bytes:
        if preserve_to_byte > 0:
            print(f"Truncating file {path} to {num_bytes} bytes")
            # copy the file up to preserve_to_byte to a temporary file in 1000 byte chunks
            temp_path = path + ".temp"
            with open(path, "rb") as f:
                with open(temp_path, "wb") as temp_f:
                    while f.tell() < preserve_to_byte:
                        temp_f.write(f.read(min(1000, preserve_to_byte - f.tell())))

        # remove the original file
        print(f"Removing {path}")
        remove(path)

        # create the file with the correct size of null bytes
        with open(path, "w") as f:
            f.write(b"\x00" * num_bytes)

        # if we copied part of the file, copy it back
        if preserve_to_byte > 0:
            print(f"Copying {temp_path} to {path}")
            with open(path, "rb") as f:
                with open(temp_path, "rb") as temp_f:
                    while True:
                        chunk = temp_f.read(1000)
                        if not chunk:
                            break
                        f.write(chunk)
