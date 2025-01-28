class Version:
    def __init__(self, major: int, minor: int, patch: int, candidate=None):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.candidate = candidate

    def __str__(self):
        if self.candidate:
            return f"{self.major}.{self.minor}.{self.patch}-{self.candidate}"
        return f"{self.major}.{self.minor}.{self.patch}"

    def __repr__(self):
        return '"' + self.__str__() + '"'

    def __gt__(self, other):
        # Compare major first
        if self.major > other.major:
            return True
        elif self.major < other.major:
            return False

        # Same major, compare minor
        if self.minor > other.minor:
            return True
        elif self.minor < other.minor:
            return False

        # Same minor, compare patch
        if self.patch > other.patch:
            return True
        elif self.patch < other.patch:
            return False

        # If self has no candidate but other does, self is "greater"
        if not self.candidate and other.candidate:
            return True

        return False

    def __lt__(self, other):
        return not self.__gt__(other) and self != other

    def __eq__(self, other):
        return self.major == other.major and self.minor == other.minor and self.patch == other.patch and self.candidate == other.candidate

    @staticmethod
    def from_str(version_str):
        """Parses 'major.minor.patch' or 'major.minor.patch-candidate' format,
        also handling candidate separated by '.'.
        Example: 1.2.3-dev or 1.2.3.dev"""
        parts = version_str.split(".", 2)
        if len(parts) < 3:
            raise ValueError(f"Version string must have at least major.minor.patch, e.g. '1.2.3' or '1.2.3-dev'. Got: {version_str}")
        patch_part = parts[2]
        candidate = None
        for sep in ["-", "."]:
            if sep in patch_part:
                patch_part, candidate = patch_part.split(sep, 1)
                break
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(patch_part)
        return Version(major, minor, patch, candidate=candidate)


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
    WHITESPACE = b" \t\n\r"

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
            if c == b"\n":
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
    end_of_content = file_size - len(last_line_bytes) - 2  # -1 for the newline at the end and another for off by one I guess

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

    pub_key = PublicKey(
        n=25850530073502007505073398889935110756716032251132404339199218781380059422255360862345198138544675141546256513054332184373517438166092251410172963421556299077069195099284810366900994760048877561951388981897823462231871242380041390062269561386306787290618184745309059687916294069920586099425145107624115989895718851520436900326103985313232359151478484869518361685407610217568258949817227423076176730822354946128428713951948845035016003414197978601744938802692314180897355778380777214605494482082206918793349659727959426652897923672356221305760483911989683767700269466619761018439625757662776289786038860327614755771099,  # noqa
        e=65537,
    )

    result = verify(hash_bytes, signature, pub_key)
    if result != "SHA-256":
        raise Exception(f"Signature invalid! {result}")


def download_update(url):
    from mrequests.mrequests import get

    response = get(
        url=url,
        headers={
            "User-Agent": "MicroPython-Device",
            "Accept": "application/octet-stream",
        },
        save_headers=True,
    )

    if response.status_code != 200:
        raise Exception(f"Failed to download update: {response.status_code} {response.reason}")

    start_percent = 2
    end_percent = 30

    total_length = 200000
    try:
        for header in response.headers:
            header_str = header.decode("utf-8")
            if "Content-Length" in header_str:
                # split on :
                total_length = int(header_str.split(":")[1].strip())
    except Exception:
        pass  # if we can't get the content length, we'll just use a default value

    percent_per_byte = (end_percent - start_percent) / total_length
    # if sflash is on board, store it in sflash
    from json import loads as json_loads

    from SPI_Store import sflash_is_on_board
    from SPI_UpdateStore import write_consumer

    # TODO sflash-based update dormant for now
    if False and sflash_is_on_board:
        # get first line
        first_lines = response.read(1024).split(b"\n")
        print(type(first_lines))
        line_1 = first_lines[0]
        print(f"First line: {line_1}")

        # parse as json
        meta_data = json_loads(line_1)

        # get incoming software version
        version = Version.from_str(meta_data.get("version", ""))
        print(f"Version: {version}")

        wc = write_consumer(f"{version.major}.{version.minor}.{version.patch}\n")
        next(wc)
        data = bytearray().join(first_lines)
        wc.send(data)
        bytes_so_far = 1024
        while chunk := response.read(1024):
            wc.send(bytearray(chunk, "utf-8"))
            bytes_so_far += len(chunk)
            yield {"percent": start_percent + (bytes_so_far * percent_per_byte)}

        try:
            wc.send(None)
        except StopIteration:
            pass

    else:
        # TODO modify this to use a buffer so we aren't recreating a buffer every loop
        # https://docs.micropython.org/en/latest/reference/constrained.html
        # look for buffers
        with open("update.json", "wb") as f:
            while chunk := response.read(1024):
                f.write(chunk)
                yield {"percent": start_percent + (f.tell() * percent_per_byte)}

    response.close()


def validate_compatibility():
    from json import loads as json_loads

    # Check if the update is compatible with the current firmware
    with open("update.json", "r") as f:
        metadata = f.readline()
        metadata = json_loads(metadata)

    # update file format
    supported_update_file_formats = ["1.0"]
    incoming_update_file_format = metadata.get("update_file_format", "")
    if incoming_update_file_format not in supported_update_file_formats:
        raise Exception(f"Update file format ({incoming_update_file_format}) not in supported formats: {supported_update_file_formats}")

    from SharedState import WarpedVersion

    current_version_obj = Version.from_str(WarpedVersion)
    supported_versions = [Version.from_str(v) for v in metadata.get("supported_software_versions", [])]
    if not any(current_version_obj == sv for sv in supported_versions):
        raise Exception(f"Version {current_version_obj} not in supported versions: {[str(v) for v in supported_versions]}")

    from sys import implementation

    mp_version_obj = Version(
        major=implementation.version[0],
        minor=implementation.version[1],
        patch=implementation.version[2],
        candidate=implementation.version[3],
    )
    supported_micropython_versions = [Version.from_str(v) for v in metadata.get("micropython_versions", [])]
    if not any(mp_version_obj == m for m in supported_micropython_versions):
        raise Exception(f"MicroPython version {mp_version_obj} not in supported versions: {[str(v) for v in supported_micropython_versions]}")

    # hardware version
    hardware = "Unknown"
    try:
        if implementation._machine == "Raspberry Pi Pico W with RP2040":
            hardware = "vector_v4"
    except Exception:
        pass

    from SPI_Store import sflash_driver_init, sflash_is_on_board

    sflash_driver_init()
    if sflash_is_on_board:
        hardware = "vector_v5"

    if hardware not in metadata.get("supported_hardware", []):
        raise Exception(f"Hardware ({hardware}) not in supported hardware list: {metadata.get('supported_hardware')}")


def apply_update(url):
    from gc import collect as gc_collect
    from time import sleep

    yield {"log": f"Downloading update from {url}", "percent": 2}
    # will yield percent updates as it downloads
    yield from download_update(url)
    gc_collect()

    yield {"log": "Validating signature", "percent": 30}
    validate_signature()
    gc_collect()

    yield {"log": "Validating compatibility", "percent": 35}
    validate_compatibility()
    gc_collect()

    yield {"log": "Writing files to board", "percent": 40}
    try:
        yield from write_files()
    except Exception as e:
        yield {"log": f"Failed to write files: {e}", "percent": 40}
        yield {"log": "Trying to write files again", "percent": 40}
        try:
            yield from write_files()
        except Exception as e:
            yield {"log": f"Failed to write files: {e}", "percent": 40}
            yield {
                "log": "The update has failed at a critical point. If you are unable to recover, please contact us for help.",
                "percent": 40,
            }
            return
    gc_collect()

    yield {"log": "Update complete, Device will now reboot", "percent": 98}
    yield {
        "log": "Web interface changes may take up to 10 minutes to show up",
        "percent": 99,
    }
    yield {
        "log": "This page should automatically reload in ~30 seconds, if not please do so manually",
        "percent": 100,
    }

    from machine import reset as machine_reset

    from reset_control import reset as reset_control

    reset_control()
    sleep(2)  # make sure the game fully shuts down and allow last messages to be finish sending
    machine_reset()


def crc16_of_file(path: str) -> str:
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

    crc = 0xFFFF
    with open(path, "rb") as file:
        while chunk := file.read(1024):
            crc = crc16_ccitt(chunk, crc)

    return f"{crc:04X}"


def write_files():
    from binascii import a2b_base64
    from json import loads as json_loads
    from os import remove

    last_line_len = len(read_last_significant_line("update.json"))
    end_of_content = 0
    with open("update.json", "rb") as f:
        f.seek(0, 2)
        end_of_content = f.tell() - last_line_len - 1

    start_percent = 40
    end_percent = 98
    percent_per_byte = end_percent - start_percent / end_of_content

    # remove_extra_files.py{"checksum":"04D9","bytes":1827,"log":"Removing extra files","execute":true}aW1wb3J0IG9zCgpr
    with open("update.json", "r") as f:
        # Skip the first line (metadata)
        f.readline()

        # loop until we reach the end of the files section
        while f.tell() < end_of_content:
            # yield a percent update
            percent = f.tell() * percent_per_byte + start_percent
            yield {"percent": percent}

            # read character by character to the first { to get the path
            path = ""
            while c := f.read(1):
                if c == "{":
                    break
                path += c

            # if path doesn't start with a / add it
            if not path.startswith("/"):
                path = "/" + path

            # read in json until the end of the object
            json_str = c
            while c := f.read(1):
                json_str += c
                if c == "}":
                    break
            metadata = json_loads(json_str)

            # file start checkpoint
            file_data_start = f.tell()

            try:
                # get the check
                current_crc16 = crc16_of_file(path)
                if current_crc16 == metadata.get("checksum", ""):
                    print(f"Skipping {path} - checksums match")
                    # skip in f until the next newline which will be the start of the next file
                    while True:
                        c = f.readline(1024)
                        if c[-1] == "\n":
                            break
                    break
            except Exception:
                # we want to skip if we can
                # but if there are any errors, we should just copy the file normally
                f.seek(file_data_start)  # jump back to the start of the file data

            # delete the original file if it exists
            try:
                remove(path)
            except OSError:
                pass

            # TODO create a buffer to write to the file
            # TODO make sure folder is created

            with open(path, "wb") as out_f:
                while True:
                    chunk = f.readline(1024)
                    # if the last character is a newline, we're done
                    if chunk[-1] == "\n":
                        out_f.write(a2b_base64(chunk[:-1]))
                        break
                    else:
                        out_f.write(a2b_base64(chunk))

            # if execute is true, run the file
            if metadata.get("execute", False):
                execute_file(path, remove_after=True)


def execute_file(path, remove_after=True):
    try:
        #  build what the import statement would look like
        module_path = path.replace("/", ".").replace(".py", "")
        if module_path.startswith("."):
            module_path = module_path[1:]
        imported_module = __import__(module_path)

        # if the module has a main function, execute it
        if hasattr(imported_module, "main"):
            imported_module.main()

        if remove_after:
            try:
                from os import remove

                remove(path)  # execute once then remove
            except OSError:
                pass  # if the file doesn't exist, that's fine
    except Exception as e:
        raise Exception(f"Failed to execute {path}: {e}")
