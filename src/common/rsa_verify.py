"""Lightweight RSA PKCS#1 v1.5 verification helpers.

This module intentionally only implements the subset of RSA needed by the
firmware: validating SHA-256 signatures with a fixed public key. The original
`rsa` dependency pulled in a full pure-Python implementation that consumed a
large amount of RAM when imported on MicroPython targets. Replacing it with
this small helper trades a little extra flash storage for a much smaller RAM
footprint during System 11 operation.
"""

from hashlib import sha256
from typing import Union

# ASN.1 DER prefix for a SHA-256 ``DigestInfo`` structure.
_SHA256_DIGESTINFO_PREFIX = bytes(
    (
        0x30,
        0x31,
        0x30,
        0x0D,
        0x06,
        0x09,
        0x60,
        0x86,
        0x48,
        0x01,
        0x65,
        0x03,
        0x04,
        0x02,
        0x01,
        0x05,
        0x00,
        0x04,
        0x20,
    )
)

BytesLike = Union[bytes, bytearray, memoryview]


def _ensure_bytes(data: BytesLike) -> bytes:
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, memoryview):
        return data.tobytes()
    raise TypeError("Data must be bytes-like")


def verify_pkcs1v15_sha256(message: BytesLike, signature: BytesLike, n: int, e: int) -> bool:
    """Return ``True`` when *signature* matches *message* under the key ``(n, e)``.

    The implementation follows RFC 8017 section 8.2.2 (RSASSA-PKCS1-v1_5
    verification) but only supports SHA-256 digests. The function performs the
    minimum amount of processing required for the firmware while avoiding any
    heap allocations beyond the decrypted signature buffer.
    """

    msg_bytes = _ensure_bytes(message)
    sig_bytes = _ensure_bytes(signature)

    digest = sha256(msg_bytes).digest()
    k = (n.bit_length() + 7) // 8

    if len(sig_bytes) > k:
        return False
    if len(sig_bytes) < k:
        sig_bytes = sig_bytes.rjust(k, b"\x00")

    signature_int = int.from_bytes(sig_bytes, "big")
    decrypted = pow(signature_int, e, n)
    em = decrypted.to_bytes(k, "big")

    if not em.startswith(b"\x00\x01"):
        return False

    try:
        separator_index = em.index(b"\x00", 2)
    except ValueError:
        return False

    padding = em[2:separator_index]
    if any(b != 0xFF for b in padding):
        return False

    digest_info = em[separator_index + 1 :]
    prefix = _SHA256_DIGESTINFO_PREFIX
    if not digest_info.startswith(prefix):
        return False

    return digest_info[len(prefix) :] == digest


__all__ = ["verify_pkcs1v15_sha256"]
