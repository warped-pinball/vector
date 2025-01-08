def find_dividers(filename, separator=b'----\n'):
    offsets = []
    offset = 0
    with open(filename, 'rb') as f:
        while True:
            line = f.readline()
            if not line:
                break
            if line == separator:
                offsets.append(offset)
            offset += len(line)
    return offsets


def validate_signature() -> bool:
    from rsa.key import PublicKey
    from rsa.pkcs1 import verify
    from binascii import a2b_base64, unhexlify
    from hashlib import sha256 as hashlib_sha256
    from json import loads as json_loads

    PUBLIC_KEY_N = 25850530073502007505073398889935110756716032251132404339199218781380059422255360862345198138544675141546256513054332184373517438166092251410172963421556299077069195099284810366900994760048877561951388981897823462231871242380041390062269561386306787290618184745309059687916294069920586099425145107624115989895718851520436900326103985313232359151478484869518361685407610217568258949817227423076176730822354946128428713951948845035016003414197978601744938802692314180897355778380777214605494482082206918793349659727959426652897923672356221305760483911989683767700269466619761018439625757662776289786038860327614755771099
    PUBLIC_KEY_E = 65537

    pub_key = PublicKey(PUBLIC_KEY_N, PUBLIC_KEY_E)
    hasher = hashlib_sha256()

    dividers = find_dividers('update.json')
    update_content_end = dividers[-1]
    
    with open('update.json', 'rb') as f:
        # calculate the hash of the file up to the last divider
        while True:
            bytes_to_read = min(1024, update_content_end - f.tell())
            chunk = f.read(bytes_to_read)
            if not chunk:
                break
            hasher.update(chunk)

        calculated_hash = hasher.digest()

        # read to next newline
        f.readline()

        # extract the check data
        check_data = json_loads(f.read(update_content_end - f.tell()))
    
    expected_hash = unhexlify(check_data['hash'])
    signature = a2b_base64(check_data['signature'])
    if calculated_hash != expected_hash:
        print('Hash mismatch')
        return False
    
    if verify(expected_hash, signature, pub_key) != 'SHA-256':
        print('Signature verification failed')
        return False
    return True

def apply_update(url):
    
    # download the file
    download_update(url)

    # validate the signature of the file
    validate_signature()

    # validate compatibility of the file
    
    
    # for line in file
        # resize the target file
        # write the new file to the target file
        # if execute==True, run it    

    # reboot the board


def check_for_updates():
    from urequests import get
    response = get(
        url =f'https://api.github.com/repos/warped-pinball/vector/releases', 
        headers={
            'User-Agent': 'MicroPython-Device',
            'Accept': 'application/vnd.github.v3+json'
        }
    )
    if response.status_code == 200:
        releases_data = response.json()
        response.close()
    else:
        raise Exception(f'Failed to fetch releases: {response.status_code}')

    # Structure the data
    structured_releases = {"releases": []}
    for release in releases_data:
        release_info = {
            "name": release.get('name', 'No name provided'),
            "tag": release.get('tag_name', 'No tag provided'),
            "prerelease": release.get('prerelease', False),
            "assets": []
        }
        # Extract asset download URLs
        assets = release.get('assets', [])
        for asset in assets:
            download_url = asset.get('browser_download_url')
            if download_url:
                release_info["assets"].append(download_url)

        structured_releases["releases"].append(release_info)
    return structured_releases

def download_update(url):
    from urequests import get
    response = get(
        url = url,
        headers={
            'User-Agent': 'MicroPython-Device',
            'Accept': 'application/octet-stream'
        },
        stream=True
    )

    if response.status_code != 200:
        raise Exception(f'Failed to download update: {response.status_code}')
    
    with open('update.json', 'w') as f:
        while True:
            chunk = response.raw.read(1024)
            if not chunk:
                break
            f.write(chunk)

    response.close()
    print('Update downloaded')        
        
    # validate the signature of the update
    # validate compatibility of the update


    # from update import download_update
    # download_update('https://github.com/warped-pinball/vector/releases/download/0.3.1/update.json')
    # with open('update.json', 'r') as f:
    #     print(f.read(1000))
