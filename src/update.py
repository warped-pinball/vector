def find_dividers(filename):
    '''
    find the byte location of the dividers in a file by scanning the file one btye at a time
    '''
    dividers = []
    with open(filename, 'rb') as f:
        file_length = f.seek(0, 2)
        f.seek(0)
        while True:
            # skip ahead to the next \n
            while True:
                if f.read(1) == b'\n':
                    break
                if f.tell() == file_length:
                    break
            # check if the next 5 bytes are ----\n
            if f.read(5) == b'----\n':
                print(dividers)
                dividers.append(f.tell())
    
    return dividers

def get_check_data():
    from hashlib import sha256 as hashlib_sha256
    from binascii import a2b_base64, unhexlify
    from json import loads as json_loads
    hasher = hashlib_sha256()

    print('Finding dividers')
    dividers = find_dividers('update.json')
    print(dividers)
    update_content_end = dividers[-1]
    
    with open('update.json', 'rb') as f:
        # calculate the hash of the file up to the last divider
        while True:
            bytes_to_read = min(1024, update_content_end - f.tell())
            chunk = f.read(bytes_to_read)
            if not chunk:
                break
            hasher.update(chunk)
        print('Hash calculated')
        calculated_hash = hasher.digest()

        # read to next newline
        f.readline()

        # extract the check data
        print('Reading check data')
        f.seek(dividers[-1] + len(b'----\n'))
        check_data = json_loads(f.read())
    
    expected_hash = unhexlify(check_data['hash'])
    signature = a2b_base64(check_data['signature'])
    return calculated_hash, expected_hash, signature

def validate_signature(hash, signature) -> bool:
    from rsa.key import PublicKey
    from rsa.pkcs1 import verify
    from logger import logger_instance as Log

    pub_key = PublicKey(
        n = 25850530073502007505073398889935110756716032251132404339199218781380059422255360862345198138544675141546256513054332184373517438166092251410172963421556299077069195099284810366900994760048877561951388981897823462231871242380041390062269561386306787290618184745309059687916294069920586099425145107624115989895718851520436900326103985313232359151478484869518361685407610217568258949817227423076176730822354946128428713951948845035016003414197978601744938802692314180897355778380777214605494482082206918793349659727959426652897923672356221305760483911989683767700269466619761018439625757662776289786038860327614755771099, 
        e = 65537
    )
    
    if verify(hash, signature, pub_key) != 'SHA-256':
        Log.log('Signature verification failed')
        return False
    return True

def apply_update(url):
    from logger import logger_instance as Log
    from gc import collect as gc_collect

    # download the file
    Log.log(f'Downloading update from {url}')
    download_update(url)    
    gc_collect()

    # get the check data
    Log.log('Getting check data')
    calculated_hash, expected_hash, signature = get_check_data()

    if calculated_hash != expected_hash:
        Log.log('Hash mismatch')
        return
    gc_collect()

    # validate the signature of the file
    Log.log('Validating signature')
    validate_signature(calculated_hash, signature)

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





# https://github.com/warped-pinball/vector/actions/runs/12663958895/artifacts/2399433428
# https://github.com/warped-pinball/vector/actions/runs/12663958895/artifacts/2399433428
# https://github.com/warped-pinball/vector/releases/download/0.3.1/update.json