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
        chunk_size = 512
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


def _public_key():
    from rsa.key import PublicKey

    return PublicKey(
        n=25850530073502007505073398889935110756716032251132404339199218781380059422255360862345198138544675141546256513054332184373517438166092251410172963421556299077069195099284810366900994760048877561951388981897823462231871242380041390062269561386306787290618184745309059687916294069920586099425145107624115989895718851520436900326103985313232359151478484869518361685407610217568258949817227423076176730822354946128428713951948845035016003414197978601744938802692314180897355778380777214605494482082206918793349659727959426652897923672356221305760483911989683767700269466619761018439625757662776289786038860327614755771099,  # noqa
        e=65537,
    )


def verify_release(latest):
    """Return the release record from latest.json once its signature checks out, otherwise raise.

    latest["signed"]["payload"] is the record as a JSON string, signed (PKCS#1 v1.5, SHA-256) with the
    same Warped Pinball key as the update files; nothing outside it is trusted.
    """
    from binascii import a2b_base64
    from json import loads as json_loads

    from rsa.pkcs1 import verify
    from systemConfig import vectorSystem

    signed = latest.get("signed") or {}
    payload = signed.get("payload")
    if not payload or not signed.get("signature"):
        raise Exception("Release information is not signed")

    try:
        result = verify(payload.encode("utf-8"), a2b_base64(signed["signature"]), _public_key())
    except Exception as e:
        raise Exception(f"Release signature invalid: {e}")
    if result != "SHA-256":
        raise Exception(f"Release signature invalid: {result}")

    release = json_loads(payload)
    if release.pop("product", None) != vectorSystem:
        raise Exception("Release is for a different system")
    return release


def fetch_latest_release():
    """latest.json comes over plain HTTP; only its signed release record is used"""
    from mrequests.mrequests import get
    from systemConfig import updatesURL

    resp = get(updatesURL, timeout=10)
    try:
        latest = resp.json()
    finally:
        resp.close()
    return verify_release(latest)


def validate_signature(skip_signature_check=False, expected_sha256=None):
    hash_bytes, expected_hash, signature = get_check_data("update.json")
    if hash_bytes != expected_hash:
        raise Exception(f"Hash mismatch - expected {expected_hash.hex()}, got {hash_bytes.hex()}")

    # Confirm this is the file we were told to expect; optional for developer builds
    if expected_sha256 and hash_bytes.hex() != str(expected_sha256).strip().lower():
        raise Exception("Update checksum does not match the expected checksum")

    if skip_signature_check:
        print("Skipping signature check")
        return

    # A release update must be the exact file the signed release record named
    if not expected_sha256:
        raise Exception("No checksum for this update")

    from rsa.pkcs1 import verify

    result = verify(hash_bytes, signature, _public_key())
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
    )

    try:
        if response.status_code != 200:
            raise Exception(f"Failed to download update: {response.status_code} {response.reason}")

        start_percent = 2
        end_percent = 30
        total_length = 500000
        buffer_size = 512
        percent_per_chunk = buffer_size * (end_percent - start_percent) / total_length

        percent = start_percent

        with open("update.json", "wb") as f:
            while True:
                chunk = response.read(buffer_size)
                if not chunk:
                    break

                f.write(chunk)

                percent += percent_per_chunk * ((end_percent - percent) / percent)
                yield {"percent": percent}
    finally:
        response.close()


class LowMemoryMode:
    def __enter__(self):
        # halt the schedule so we aren't allocating ram for other tasks
        import phew.server

        phew.server._halt_schedule = True

        # drop the state for discovery since we can recover it
        try:
            import discovery

            discovery.send_sock.close()
            discovery.recv_sock.close()

            discovery.send_sock = None
            discovery.recv_sock = None

            discovery.known_devices = []
        except Exception as e:
            print("Unable to shut down discovery sockets:", e)

        from gc import collect as gc_collect

        gc_collect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # reintroduce ourselves and reinitialize the sockets
        try:
            from discovery import broadcast_hello, listen

            broadcast_hello()
            listen()
        except Exception as e:
            print("Unable to reinitialize discovery sockets:", e)

        # resume the task schedule
        try:
            import phew.server

            phew.server._halt_schedule = False
            phew.server.restart_schedule()
        except Exception as e:
            print("Unable to restart task schedule:", e)

        return False  # don't suppress exceptions


def _remove_update_file():
    from os import remove

    try:
        remove("update.json")
    except OSError:
        pass


def apply_update(url, skip_signature_check=False, expected_sha256=None):
    with LowMemoryMode():
        from gc import collect as gc_collect
        from time import sleep

        yield {"log": f"Downloading update from {url}", "percent": 2}
        try:
            # will yield percent updates as it downloads
            yield from download_update(url)
            gc_collect()

            yield {"log": "Validating signature and checksum", "percent": 30}
            validate_signature(skip_signature_check=skip_signature_check, expected_sha256=expected_sha256)
        except Exception:
            # a refused or partial download is never used, so don't leave it taking up flash
            _remove_update_file()
            raise
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

        yield {"log": "Update complete, Device will now reboot", "percent": 99}
        yield {
            "log": "This page should automatically reload in ~30 seconds, if not please do so manually",
            "percent": 100,
        }

        from machine import reset as machine_reset
        from reset_control import reset as reset_control

        reset_control()
        sleep(2)  # make sure the game fully shuts down and allow last messages to be finish sending
        machine_reset()


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
    percent_per_byte = (end_percent - start_percent) / end_of_content

    # remove_extra_files.py{"checksum":"04D9","bytes":1827,"log":"Removing extra files","execute":true}aW1wb3J0IG9zCgpr
    with open("update.json", "r") as f:
        # Skip the first line (metadata)
        f.readline()

        # loop until we reach the end of the files section
        while f.tell() < end_of_content:
            # read character by character to the first { to get the path
            path = ""
            while c := f.read(1):
                if c == "{":
                    break
                path += c

            # if path doesn't start with a / add it
            if not path.startswith("/"):
                path = "/" + path

            # create the folder structure if it doesn't exist
            from os import mkdir

            parts = path.strip("/").split("/")[:-1]
            current = ""
            for part in parts:
                current += "/" + part
                try:
                    mkdir(current)
                except OSError:
                    pass

            # yield a percent update
            percent = f.tell() * percent_per_byte + start_percent
            yield {"log": f"Writing {path}", "percent": percent}

            # read in json until the end of the object
            json_str = c
            while c := f.read(1):
                json_str += c
                if c == "}":
                    break
            metadata = json_loads(json_str)

            # delete the original file if it exists
            try:
                remove(path)
            except OSError:
                pass

            # write the file
            with open(path, "wb") as out_f:
                while True:
                    # I tried using a buufer here, but it's very tricky
                    chunk = f.readline(200)
                    if not chunk:
                        break
                    if chunk.endswith("\n"):
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
