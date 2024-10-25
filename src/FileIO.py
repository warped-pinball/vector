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


#file upload.  can include directories int the file name if the directory already exists
#  ex:  "phew/test.py"
#browser side (java script) calls once for each file structure inside of download file
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

    
       
