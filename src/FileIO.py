"""
file operations generally for the admin page
V12/9/2024 support for software download
"""
import gc
import json

import SPI_DataStore as DataStore
from logger import logger_instance

Log = logger_instance


def download_scores():
    data = []

    data.append(
        {
            "FileType": "leaders",
            "contents": [DataStore.read_record("leaders", i) for i in range(DataStore.memory_map["leaders"]["count"])],
        }
    )

    data.append(
        {
            "FileType": "tournament",
            "contents": [DataStore.read_record("tournament", i) for i in range(DataStore.memory_map["tournament"]["count"])],
        }
    )

    return json.dumps(data)


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
