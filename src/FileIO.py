'''
file operations generally for the admin page
V12/9/2024 support for software download
'''
import gc
import json
import SPI_DataStore as DataStore
import os
import SharedState as S
from logger import logger_instance
import ubinascii
Log = logger_instance

def download_scores():
    data = []
    
    data.append({
        "FileType": "leaders",
        "contents": [
            DataStore.read_record("leaders", i) for i in range(DataStore.memory_map["leaders"]["count"])
        ]
    })

    data.append({
        "FileType": "tournament",
        "contents": [
            DataStore.read_record("tournament", i) for i in range(DataStore.memory_map["tournament"]["count"])
        ]
    })

    
    return json.dumps(data)


#download the list of players
def download_names(request):
    gc.collect()
    print("download names - - - ")
    try:
        # Collect player names data
        names_data = [DataStore.read_record("names", i) for i in range(DataStore.memory_map["names"]["count"])]

        response_body = [{
            "FileType": "names",
            "contents": names_data
        }]
        # Prepare the final response
        response = {
            'headers': {
                'Content-Type': 'application/json',
                'Content-Disposition': 'attachment; filename=names.json',
                'Connection': 'close'
            },
            'body': json.dumps(response_body)
        }
        return json.dumps(response)

    except Exception as e:
        print(f"Error generating download: {e}")
        return json.dumps({
            'headers': {
                'Content-Type': 'application/json',
                'Connection': 'close'
            },
            'body': json.dumps({"error": "An error occurred while generating the download."})
        })



def download_log():
    try:
        # Prepare the response headers
        headers = {
            'Content-Type': 'text/plain',
            'Content-Disposition': 'attachment; filename=log.txt',
            'Connection': 'close'
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
    return '{:04X}'.format(crc_value)

# Base64 decoding function for MicroPython
def base64_decode(data):
    """Decode a Base64 encoded string into bytes."""
    import ubinascii
    return ubinascii.a2b_base64(data)


download_results = "File Index List: "

#file upload
def process_incoming_file(request):
    import gc
    import json
    import ubinascii
    global download_results

    # Base64 decoding for MicroPython
    def base64_decode(data):
        """Decode a Base64 encoded string into bytes."""
        return ubinascii.a2b_base64(data)

    gc.collect()
    try:
        form_data = request.form
        for key in form_data:
            value = form_data[key]

        gc.collect()

        data = json.loads(value)
        file_type = data.get("FileType")
        contents = data.get("contents")
        received_checksum = data.get("Checksum")
        is_binary = data.get("Binary", False)  #default to text if missing
        append = data.get("append", 1)  # Default to 1 if "append" is missing
        index = data.get("index",1)
              
        #check for match to fram data store first - - 
        if file_type in DataStore.memory_map:      
            Log.log(f"FIO: Datastore file in: {file_type}")              
            for idx, record in enumerate(contents):           
                #print("FIO: ",idx)         
                DataStore.write_record(file_type, record, idx)
            download_results += f" {file_type}"
            return "Upload complete" #**************************************

        Log.log(f"FIO: Load file: {file_type}, I{index} A{append}{' B' if is_binary else ''}")

        if is_binary:        
            contents = base64_decode(contents)
            calculated_checksum = crc16(contents)  # Use raw binary data
        else:
            calculated_checksum = crc16(contents.encode('utf-8'))  # Encode as UTF-8

        # Verify checksum
        received_checksum = received_checksum.lower()
        calculated_checksum = f"{calculated_checksum}".lower()

        if calculated_checksum != received_checksum:
            Log.log(f"FIO: Checksum fail. Expected {received_checksum}, got {calculated_checksum}")            
        else:
            print("FIO: Checksum good:", f"{calculated_checksum}")
        
        save_path = f"{file_type}"  
        print("FIO: Save Path: ",save_path)

        # Determine file mode based on append value
        #mode = 'ab' if append > 1 else 'wb' if is_binary else 'a' if append > 1 else 'w'
        if append > 1:
            mode = 'ab' if is_binary else 'a'
        else:
            mode = 'wb' if is_binary else 'w'


        # Save file
        with open(save_path, mode) as f:
            f.write(contents if is_binary else contents.encode('utf-8'))
        print(f"FIO: File {'appended' if append > 1 else 'saved'}: {file_type}")

        gc.collect()

        # If it's RunMe.py (must fit in one chunk!)
        if file_type == "RunMe.py":
            print("FIO: Executing RunMe.py")
            module_name = "RunMe"
            imported_module = __import__(module_name)
            try:
                result = imported_module.go()  # Call the main function
                download_results += f" RM "
                if result is not None:
                    Log.log(f"FIO: RunMe returned {result}")
                    S.update_load_result = result
                else:
                    Log.log("FIO: RunMe executed, no return value")
            except ImportError as e:
                print(f"FIO: Error importing module {module_name}: {e}")
            except Exception as e:
                print(f"FIO: An error occurred while running {module_name}.go(): {e}")
        else:
            download_results += f"{index} "

        return "Upload complete"

    except Exception as e:
        Log.log(f"Error processing file upload: {e}")
        S.update_load_result=("FIO: General Fault")
        return f"An error occurred: {e}"


def incoming_file_results(request):
    global download_results
    S.update_load_result = download_results
    download_results = "File Index List: "
    if S.update_load_result is None:
        return "Nothing to report"
    else:
        return S.update_load_result

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
        with open(path, 'rb+') as f:
            f.seek(0, 2)
            file_size = f.tell()
            
            # if it's smaller than the final size, pad it with null bytes
            if file_size < num_bytes:
                print(f"Padding file {path} with {num_bytes - file_size} null bytes")
                f.write(b'\x00' * (num_bytes - file_size))
                file_size = num_bytes

    # catch ENOENT exception
    except OSError as e:
        # if the file does not exist, create it with the correct size
        with open(path, 'w') as f:
            print(f"Creating file {path} with {num_bytes} null bytes")
            f.write(b'\x00' * num_bytes)
            file_size = num_bytes
    except Exception as e:
        raise e

    # if the file exists, but is too large
    if file_size > num_bytes:
        if preserve_to_byte > 0:
            print(f"Truncating file {path} to {num_bytes} bytes")
            # copy the file up to preserve_to_byte to a temporary file in 1000 byte chunks
            temp_path = path + ".temp"
            with open(path, 'rb') as f:
                with open(temp_path, 'wb') as temp_f:
                    while f.tell() < preserve_to_byte:
                        temp_f.write(f.read(min(1000, preserve_to_byte - f.tell())))
        
        # remove the original file
        print(f"Removing {path}")
        remove(path)
    
        # create the file with the correct size of null bytes
        with open(path, 'w') as f:
            f.write(b'\x00' * num_bytes)

        # if we copied part of the file, copy it back
        if preserve_to_byte > 0:
            print(f"Copying {temp_path} to {path}")
            with open(path, 'rb') as f:
                with open(temp_path, 'rb') as temp_f:
                    while True:
                        chunk = temp_f.read(1000)
                        if not chunk:
                            break
                        f.write(chunk)

       
