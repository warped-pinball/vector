# RunMe
import os

import SPI_DataStore as datastore
from logger import logger_instance

Log = logger_instance


def copy_file(src_file, dest_file):
    # Open the source file in read-binary mode and destination file in write-binary mode
    with open(src_file, "rb") as src:
        with open(dest_file, "wb") as dest:
            # Read and write the file in chunks
            while True:
                buffer = src.read(1024)  # Read 1024 bytes at a time
                if not buffer:
                    break
                dest.write(buffer)


def copy_specific_files_to_root(file_list, src_dir="/test", dest_dir="/"):
    for file in file_list:
        src_file = src_dir + "/" + file
        dest_file = dest_dir + "/" + file

        # Extract directory path from the destination file path
        dest_path = "/".join(dest_file.split("/")[:-1])

        print(src_file, "  ", dest_file)

        # Check if the destination directory exists
        try:
            os.listdir(dest_path)
        except OSError:
            Log.log(f"RunMe: Destination directory {dest_path} does not exist")
            return False

        # Check if the source file exists
        try:
            with open(src_file, "rb"):
                pass
        except OSError:
            Log.log(f"RunMe: Source file {src_file} does not exist")
            return False
        try:
            Log.log(f"RunMe: Copying {src_file} to {dest_file}")
            copy_file(src_file, dest_file)
            continue
        except Exception as e:
            print(e)
            Log.log("RunMe: Copy fail")
            return False


def go():
    # List of specific files to copy (relative to the src_dir)
    files_to_copy = ["nothing.py"]
    try:
        copy_specific_files_to_root(files_to_copy)
        Log.log("RunMe: Files copied to root")
    except Exception as e:
        print(e)
        Log.log("RunMe: fault return from copy files")

    # change conf'd game
    config = datastore.read_record("configuration")
    config["gamename"] = "GenericSystem11"
    datastore.write_record("configuration", config)
    Log.log("RunMe: Generic sys11 configured")

    return "test string for return\nsecond line here...\nthree"
