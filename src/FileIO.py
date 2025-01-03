'''
file operations generally for the admin page

'''
import gc
import json
import SPI_DataStore as DataStore
import os
import SharedState as S
from logger import logger_instance
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


#file upload.  can include directories int the file name if the directory already exists
#  ex:  "phew/test.py"
#browser side (java script) calls once for each file structure inside of download file


#TODO update file format
    # once-per-file keys:
        # update_file_format: version of the update file format
        # supported_hardware_versions: list of hardware versions supported by the update
        # supported_software_versions: list of software versions supported by the update
        # version: what version of the software this update contains
        # full_checksum: checksum of all files that should be on the board after the update, excluding any custom files
        # board_signature: signed copy of the full_checksum to validate who created the update
        # js_signature: signed copy of a hash of the files in the update to validate within the web UI
    # per-file/chunk keys in key ('files') list:
        # required keys:
            # path: path to the file including the file name
            # checksum: checksum of the file data note: cumulative checksum of all previous chunks
            # data: base 85 encoded file data
        # optional keys:
            # part_number: part number of the file being uploaded (1-indexed, 1 implies do not append; overwrite)
            # total_parts: total number of parts for the file
            # compressed: int, level of compression applied to the file data. 0 or none implies no compression
            # log: for web UI only, message to display to user ex: "uploading file 1 of 10"
            # execute: command to run after the file is uploaded, ex: "import RunMe; RunMe.go()"


#TODO steps the update process should take:

# confirm update supports the hardware and software 421
    
# delete all files not present in the update (possibly exceptions for custom uploaded files)

# hash all remaining files and return to web UI

# web UI uploads just the files that have changed by checking the checksums:
    # all files in bytes-like format
    # update build process options to support:
        # optional compression & decompression of files
        # optionally group small files into a single request






def process_incoming_file(request):   
    gc.collect()    
    print("incomming")
    try:    
        form_data = request.form        
        #key is a strange form from browser, look for generic key
        for key in form_data:
            value = form_data[key]

        data = json.loads(value)    
        file_type=data.get("FileType")
        contents =data.get("contents")
        received_checksum = data.get("Checksum")
        Log.log(f"FIO: load file: {file_type}")        

        if file_type.endswith(".mpy"):
            contents = contents.encode('latin1')
            if received_checksum:
                calculated_checksum = crc16(contents)
        elif file_type.endswith(".py") or file_type.endswith(".json"):
            if received_checksum:
                calculated_checksum = crc16(contents.encode('utf-8'))        

        if received_checksum:
            if calculated_checksum != received_checksum:
                Log.log("FIO: checksum fail")
                raise ValueError(f"FIO: Checksum fail Expected {received_checksum}, got {calculated_checksum}")
            else:
                print("FIO: Checksum good: ", calculated_checksum)

        save_path = f"/test/{file_type}"    
        if file_type=="RunMe.py":
             save_path = f"{file_type}"    

        if file_type.endswith(".py") or file_type.endswith(".json"):    #text
            with open(save_path, 'w') as f:                               
                f.write(contents)
            print(f"FIO: File saved: {file_type}")      
        elif file_type.endswith(".mpy"):                                #binary
            with open(save_path, 'wb') as f:
                f.write(contents)
            print(f"FIO: Binary file saved: {file_type}")
        else:   
            print("FIO: process file as datastore: ", file_type)    
            if file_type in DataStore.memory_map:      
                Log.log(f"FIO: Datastore file in: {file_type}")              
                #TODO what happens if the contents are longer than the record size?
                for idx, record in enumerate(contents):           
                    print("FIO: ",idx)         
                    DataStore.write_record(file_type, record, idx)
        gc.collect()                

        #file... RunMe?        
        if file_type=="RunMe.py":
            print("Run me now")
            module_name = "RunMe"            
            imported_module = __import__(module_name)
            try:
                result = imported_module.go()  # Call the main function
                if result is not None:
                    Log.log(f"FIO: RunMe returned {result}")
                    #store result
                    S.update_load_result = result
                else:
                    Log.log("FIO: RunMe executed, no return value")
            except ImportError as e:
                print(f"FIO: Error importing module {module_name}: {e}")
            except Exception as e:
                print(f"FIO: An error occurred while running {module_name}.go(): {e}")
      
        return ("Upload complete")  

    except Exception as e:
        print(f"Error processing file upload: {e}")
        return (f"An error occurred: {e}")


def incoming_file_results(request):
    if S.update_load_result is None:
        return ("Nothing to report")
    else:
        return S.update_load_result

#
#use this to build files or file sets for uploading
#
def process_files(files):
    combined_data = []
    gname = "11" #S.gdata["GameInfo"]["GameName"]

    print(files)

    if isinstance(files, str):
        files = [files]  
    
    for file in files:
        gc.collect()
        
        if file.endswith('.mpy'):
            mode = 'rb'
        else:
            mode = 'r'

        with open(file, mode) as f:
            data = f.read() 
            
            if mode == 'rb':
                checksum = crc16(data)
                contents = data.decode('latin1')  
            else:
                checksum = crc16(data.encode('utf-8'))
                contents = data

            combined_data.append({
                "FileType": file,
                "GameName": gname,
                "Version": S.WarpedVersion,
                "contents": data,
                "Checksum": checksum
            })
    
    return json.dumps(combined_data)


if __name__ == "__main__":
    print("combine files")
    gc.collect()

    files_to_copy = [
        'nothing.py'
    ]    

    files_to_copy += ['RunMe.py']
    combined_data = process_files(files_to_copy)    
    print (combined_data)
    with open("combined_files.json", 'w') as f:
        f.write(combined_data)

    
       
