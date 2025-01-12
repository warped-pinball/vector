import binascii

import urandom


def random_bytes(n):
    output = urandom.getrandbits(8).to_bytes(1, "big")
    for i in range(n - 1):
        output += urandom.getrandbits(8).to_bytes(1, "big")
    return output


def random_hex(n):
    return binascii.hexlify(random_bytes(n)).decode()


# TODO is this dead code?
