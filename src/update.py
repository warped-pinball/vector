def check_for_updates():
    from urequests import get
    response = get(
        url="https://api.github.com/repos/warped-pinball/vector/releases",
        headers={
            "User-Agent": "MicroPython-Device",
            "Accept": "application/vnd.github.v3+json"
        }
    )
    if response.status_code == 200:
        releases_data = response.json()
        response.close()
    else:
        raise Exception(f"Failed to fetch releases: {response.status_code}")

    structured_releases = {"releases": []}
    for release in releases_data:
        release_info = {
            "name": release.get("name", "No name provided"),
            "tag": release.get("tag_name", "No tag provided"),
            "prerelease": release.get("prerelease", False),
            "assets": []
        }
        assets = release.get("assets", [])
        for asset in assets:
            download_url = asset.get("browser_download_url")
            if download_url:
                release_info["assets"].append(download_url)

        structured_releases["releases"].append(release_info)
    return structured_releases


def read_last_significant_line(path):
    """
    Returns the last non-whitespace line from 'path' in bytes.
    
    Algorithm:
      1. Seek to end of file, skipping all trailing whitespace (b'\\n', b'\\r', b' ', etc.).
      2. Once found a non-whitespace char, mark that as end_of_line.
      3. Continue backward until we find a b'\\n' or reach the beginning of the file.
      4. The line is then the region (start_of_line..end_of_line).
      5. If the entire file is whitespace, return b"".
    """
    WHITESPACE = b' \t\n\r'
    
    with open(path, "rb") as f:
        # Step A: find file size
        f.seek(0, 2)
        file_size = f.tell()
        if file_size == 0:
            return b""  # empty file => no line

        # Step B: skip trailing whitespace
        # We'll move backward from the end until we find a non-whitespace char
        end_pos = file_size
        while end_pos > 0:
            end_pos -= 1
            f.seek(end_pos, 0)
            c = f.read(1)
            if c not in WHITESPACE:
                # Found a non-whitespace char
                # => The last line ends at end_pos + 1
                end_pos += 1
                break
        else:
            # If we never broke from the loop, the entire file is whitespace
            return b""

        # Step C: from that end_pos, keep moving backward until we find b'\n' or reach start of file
        start_pos = end_pos
        while start_pos > 0:
            start_pos -= 1
            f.seek(start_pos, 0)
            c = f.read(1)
            if c == b'\n':
                # The line starts after this newline
                start_pos += 1
                break

        # Step D: read from start_pos..end_pos
        length = end_pos - start_pos
        f.seek(start_pos, 0)
        line_bytes = f.read(length)
        return line_bytes


def get_check_data(path="update.json"):
    import json
    from binascii import a2b_base64, unhexlify
    from hashlib import sha256

    # 1) Read the last non-whitespace line
    last_line_bytes = read_last_significant_line(path)
    if not last_line_bytes:
        # If empty, file might be incomplete or no signature line
        raise ValueError("Could not find a valid last line in the update file.")
    
    # print out the last line as str
    print(f"Last line: {last_line_bytes.decode('utf-8')}")

    # 2) Compute the hash excluding that line
    with open(path, "rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
    end_of_content = file_size - len(last_line_bytes) - 2 # -1 for the newline at the end and another for off by one I guess
    print(f"End of content: {end_of_content}")

    # We do a chunk-based read up to 'end_of_content'
    hasher = sha256()
    with open(path, "rb") as f:
        to_read = end_of_content
        chunk_size = 1024
        while to_read > 0:
            read_now = min(chunk_size, to_read)
            chunk = f.read(read_now)
            if not chunk:
                break
            hasher.update(chunk)
            to_read -= len(chunk)

    calculated_hash = hasher.digest()

    # 3) Parse the last line as JSON => get sha256, signature
    line_str = last_line_bytes.decode("utf-8").strip()
    sig_obj = json.loads(line_str)
    expected_hash = unhexlify(sig_obj.get("sha256", ""))
    signature = a2b_base64(sig_obj.get("signature", ""))

    return calculated_hash, expected_hash, signature

def validate_signature():
    hash_bytes, expected_hash, signature = get_check_data("update.json")
    if hash_bytes != expected_hash:
        raise Exception(f"Hash mismatch - expected {expected_hash}, got {hash_bytes}")
    
    from rsa.key import PublicKey
    from rsa.pkcs1 import verify
    from logger import logger_instance as Log

    pub_key = PublicKey(
        n=25850530073502007505073398889935110756716032251132404339199218781380059422255360862345198138544675141546256513054332184373517438166092251410172963421556299077069195099284810366900994760048877561951388981897823462231871242380041390062269561386306787290618184745309059687916294069920586099425145107624115989895718851520436900326103985313232359151478484869518361685407610217568258949817227423076176730822354946128428713951948845035016003414197978601744938802692314180897355778380777214605494482082206918793349659727959426652897923672356221305760483911989683767700269466619761018439625757662776289786038860327614755771099,
        e=65537
    )
    
    result = verify(hash_bytes, signature, pub_key)
    if result != 'SHA-256':
        raise Exception(f"Signature invalid! {result}")

def download_update(url):
    from urequests import get
    response = get(
        url=url,
        headers={
            "User-Agent": "MicroPython-Device",
            "Accept": "application/octet-stream"
        },
        stream=True
    )

    if response.status_code != 200:
        raise Exception(f"Failed to download update: {response.status_code} {response.reason}")

    with open("update.json", "wb") as f:
        while True:
            chunk = response.raw.read(1024)
            if not chunk:
                break
            f.write(chunk)

    response.close()
    print("Update downloaded")

def validate_compatibility():
    from json import load as json_load

    # Check if the update is compatible with the current firmware
    with open("update.json", "r") as f:
        data = json_load(f.readline())

    # update file format
    supported_update_file_formats = ["1.0"]
    incoming_update_file_format = data.get("update_file_format", "")
    if not incoming_update_file_format in supported_update_file_formats:
        raise Exception(f"Update file format ({incoming_update_file_format}) not in supported formats: {supported_update_file_formats}")
    
    # warped pinball version
    from SharedState import WarpedVersion
    if WarpedVersion not in data.get("supported_software_versions", []):
        raise Exception(f"Version {WarpedVersion} not in supported versions: {data.get('supported_software_versions')}")
    
    # micopython version
    from sys import implementation
    mp_version = ".".join([str(e) for e in implementation.version])
    if mp_version not in data.get("micropython_versions", []):
        raise Exception(f"MicroPython version {mp_version} not in supported versions: {data.get('micropython_versions')}")

    # hardware version
    hardware = "Unknown"
    try:
        if implementation._machine == 'Raspberry Pi Pico W with RP2040':
            hardware = "vector_v4"
    except Exception as e:
        pass
    #TODO implement flash chip check
    has_sflash = True
    if has_sflash:
        hardware = "vector_v5"

    if not hardware in data.get("supported_hardware", []):
        raise Exception(f"Hardware ({hardware}) not in supported hardware list: {data.get('supported_hardware')}")

def apply_update(url):
    from logger import logger_instance as Log
    from gc import collect as gc_collect

    Log.log(f"Downloading update from {url}")
    download_update(url)
    gc_collect()

    Log.log("Validating update")
    validate_signature()
    gc_collect()
    
    Log.log("Checking compatibility")
    validate_compatibility()
    gc_collect()
    

    Log.log("Copying files")
    copy_files()
    

def copy_files():
    from json import loads as json_loads
    from os import remove
    from binascii import a2b_base64

    last_line_len = len(read_last_significant_line("update.json"))
    with open("update.json", "rb") as f:
        f.seek(0, 2)
        end_of_content = f.tell() - last_line_len - 1
        

    # remove_extra_files.py{"checksum":"04D9","bytes":1827,"log":"Removing extra files","execute":true}aW1wb3J0IG9zCgpr
    with open("update.json", "r") as f:
        # Skip the first line (metadata)
        f.readline()

        # loop until we reach the end of the files section
        while f.tell() < end_of_content:
            # read character by character to the first { to get the path
            path = ""
            while True:
                c = f.read(1)
                if c == "{":
                    break
                path += c
            
            # read in json until the end of the object
            json_str = c
            while True:
                c = f.read(1)
                json_str += c
                if c == "}":
                    break
            metadata = json_loads(json_str)

            # TODO skip on matched checksum

            # delete the original file if it exists
            try:
                remove(path)
            except OSError:
                pass

            with open(path, "wb") as out_f:
                while chars_remaining > 0:
                    chunk = f.readline(1024)
                    out_f.write(a2b_base64(chunk))
                    # if the last character is a newline, we're done
                    if chunk[-1] == "\n":
                        break
                    chars_remaining -= len(chunk)

            # if execute is true, run the file
            if metadata.get("execute", False):
                try:
                    #  build what the import statement would look like
                    module_path = path.replace("/", ".").replace(".py", "")
                    if module_path.startswith("."):
                        module_path = module_path[1:]
                    imported_module = __import__(module_path)

                    # if the module has a main function, execute it
                    if hasattr(imported_module, "main"):
                        imported_module.main()

                    try:
                        from os import remove
                        remove(path) # execute once then remove
                    except OSError:
                        pass # if the file doesn't exist, that's fine
                except Exception as e:
                    #TODO should we make an option to indiacte if we should continue or not on error?
                    raise Exception(f"Failed to execute {path}: {e}")


                
                
                
                
            

            