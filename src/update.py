import json
import os
from binascii import a2b_base64, unhexlify
from hashlib import sha256 as hashlib_sha256

def read_last_line(path):
    """
    Read the last line from 'path' by seeking from the end
    and scanning backwards for b'\\n'.
    """
    with open(path, "rb") as f:
        f.seek(0, 2)
        file_size = f.tell()

        read_pos = file_size
        while read_pos > 0:
            read_pos -= 1
            f.seek(read_pos)
            byte = f.read(1)
            if byte == b'\n':
                start_of_line = read_pos + 1
                f.seek(start_of_line)
                return f.read(file_size - start_of_line)
        # No newline found => entire file is last line
        f.seek(0)
        return f.read(file_size)

def compute_hash_excluding_last_line(path):
    """
    Compute a SHA-256 over everything except the last line.
    """
    with open(path, "rb") as f:
        f.seek(0, 2)
        file_size = f.tell()

    last_line = read_last_line(path)
    last_line_len = len(last_line)
    end_of_content = file_size - last_line_len
    print("End of content:", end_of_content)

    hasher = hashlib_sha256()
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

    print("Hashed content")
    return hasher.digest()

def get_check_data(path="update.json"):
    """
    - Hash all content except last line.
    - Parse last line as signature JSON.
    - Return (calculated_hash, expected_hash, signature).
    """
    calculated_hash = compute_hash_excluding_last_line(path)
    print("Calculated hash:", calculated_hash)
    # parse last line => signature data
    last_line_bytes = read_last_line(path)
    sig_obj = json.loads(last_line_bytes.decode("utf-8").strip())

    expected_hash = unhexlify(sig_obj.get("sha256", ""))  # from hex to bytes
    signature = a2b_base64(sig_obj.get("signature", ""))  # from base64 to bytes
    return calculated_hash, expected_hash, signature

def validate_signature(hash_bytes, signature) -> bool:
    from rsa.key import PublicKey
    from rsa.pkcs1 import verify
    from logger import logger_instance as Log

    pub_key = PublicKey(
        n=25850530073502007505073398889935110756716032251132404339199218781380059422255360862345198138544675141546256513054332184373517438166092251410172963421556299077069195099284810366900994760048877561951388981897823462231871242380041390062269561386306787290618184745309059687916294069920586099425145107624115989895718851520436900326103985313232359151478484869518361685407610217568258949817227423076176730822354946128428713951948845035016003414197978601744938802692314180897355778380777214605494482082206918793349659727959426652897923672356221305760483911989683767700269466619761018439625757662776289786038860327614755771099,
        e=65537
    )
    
    result = verify(hash_bytes, signature, pub_key)
    if result != 'SHA-256':
        return False
    return True

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

def apply_update(url):
    from logger import logger_instance as Log
    from gc import collect as gc_collect

    Log.log(f"Downloading update from {url}")
    download_update(url)
    gc_collect()

    # get_check_data -> (calculated_hash, expected_hash, signature)
    Log.log("Getting check data")
    calculated_hash, expected_hash, signature = get_check_data("update.json")
    if calculated_hash != expected_hash:
        Log.log("Hash mismatch!")
        return

    Log.log("Validating signature")
    if not validate_signature(calculated_hash, signature):
        Log.log("Signature invalid!")
        return

    # If we reach here, signature is valid and hash matches
    Log.log("Signature verified, applying update...")

    # ... do stuff: parse lines, create files, run code, etc. ...
    # e.g. read "update.json" lines except the last line
    # or follow your existing approach for each line
    # once done, maybe reboot or exit
    Log.log("Update applied successfully.")
