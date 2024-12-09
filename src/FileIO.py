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
Log = logger_instance


def pretty_json(data, indent=4):
    return json.dumps(data).replace('{', '{\n' + ' ' * indent).replace('}', '\n' + ' ' * indent + '}').replace('[', '[\n' + ' ' * indent).replace(']', '\n' + ' ' * indent + ']').replace(',', ',\n' + ' ' * indent)

# download leader board
def download_leaders(request):
    print("download leaders - - - ")
    try:
        leaders = [DataStore.read_record("leaders", i) for i in range(DataStore.memory_map["leaders"]["count"])]
        response_body = [{
            "FileType": "leaders",
            "contents": leaders
        }]
        response = {
            'headers': {
                'Content-Type': 'application/json',
                'Content-Disposition': 'attachment; filename=leaders.json',
                'Connection': 'close'
            },
            'body': pretty_json(response_body)
        }
        return json.dumps(response)    
    except Exception as e:
        print(f"Error generating download: {e}")
        error_response = {
            'headers': {
                'Content-Type': 'application/json',
                'Connection': 'close'
            },
            'body': json.dumps({"error": "An error occurred while generating the download."})
        }
        return json.dumps(error_response)


#download the tournament board
def download_tournament(request):
    gc.collect()
    print("download tournament - - - ")
    try:
        tournament_data = [DataStore.read_record("tournament", i) for i in range(DataStore.memory_map["tournament"]["count"])]
        response_body = [{
            "FileType": "tournament",
            "contents": tournament_data
        }]
        response = {
            'headers': {
                'Content-Type': 'application/json',
                'Content-Disposition': 'attachment; filename=tournament.json',
                'Connection': 'close'
            },
            'body': json.dumps(response_body)
        }
        return json.dumps(response)    
    except Exception as e:
        print(f"Error generating download: {e}")
        error_response = {
            'headers': {
                'Content-Type': 'application/json',
                'Connection': 'close'
            },
            'body': json.dumps({"error": "An error occurred while generating the download."})
        }
        return json.dumps(error_response)


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


def download_log(request):
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


#file upload.  can include directories int the file name if the directory already exists
#  ex:  "phew/test.py"
#browser side (java script) calls once for each file structure inside of download file
def process_incoming_file(request):
    import gc
    import json
    import ubinascii

    # Base64 decoding for MicroPython
    def base64_decode(data):
        """Decode a Base64 encoded string into bytes."""
        return ubinascii.a2b_base64(data)

    gc.collect()
    try:
        form_data = request.form

        # Extract the file data from the form
        for key in form_data:
            value = form_data[key]

        gc.collect()

        data = json.loads(value)
        file_type = data.get("FileType")
        contents = data.get("contents")
        received_checksum = data.get("Checksum")
        is_binary = data.get("Binary", False)
        append = data.get("append", 1)  # Default to 1 if "append" is missing

        Log.log(f"FIO: Load file: {file_type}, append={append}")

        # Process content based on Binary flag
        if is_binary:        
            contents = base64_decode(contents)
            if received_checksum:
                calculated_checksum = crc16(contents)  # Use raw binary data
        else:
            if received_checksum:
                calculated_checksum = crc16(contents.encode('utf-8'))  # Encode as UTF-8

        # Verify checksum
        #if received_checksum:
        received_checksum = received_checksum.lower()
        calculated_checksum = f"{calculated_checksum}".lower()

        if calculated_checksum != received_checksum:
            Log.log("FIO: Checksum fail")
            raise ValueError(
                f"FIO: Checksum fail. Expected {received_checksum}, got {calculated_checksum}"
            )
        else:
            print("FIO: Checksum good:", f"{calculated_checksum}")

        # Define save path
        save_path = f"{file_type}"  # Place directly in root directory
        if file_type == "RunMe.py":
            save_path = f"{file_type}"

        print(save_path)

        # Determine file mode based on append value
        mode = 'ab' if append > 1 else 'wb' if is_binary else 'a' if append > 1 else 'w'

        # Save file
        with open(save_path, mode) as f:
            f.write(contents if is_binary else contents.encode('utf-8'))
        print(f"FIO: File {'appended' if append > 1 else 'saved'}: {file_type}")

        gc.collect()

        # If it's RunMe.py and the final append, execute it
        if file_type == "RunMe.py" and append == 1:
            print("Executing RunMe.py")
            module_name = "RunMe"
            imported_module = __import__(module_name)
            try:
                result = imported_module.go()  # Call the main function
                if result is not None:
                    Log.log(f"FIO: RunMe returned {result}")
                    S.update_load_result = result
                else:
                    Log.log("FIO: RunMe executed, no return value")
            except ImportError as e:
                print(f"FIO: Error importing module {module_name}: {e}")
            except Exception as e:
                print(f"FIO: An error occurred while running {module_name}.go(): {e}")

        return "Upload complete"

    except Exception as e:
        print(f"Error processing file upload: {e}")
        return f"An error occurred: {e}"



def incoming_file_results(request):
    if S.update_load_result is None:
        return "Nothing to report"
    else:
        return S.update_load_result

       
