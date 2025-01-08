# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2011 Sybren A. Stüvel <sybren@stuvel.eu>
#
# SPDX-License-Identifier: Apache-2.0

"""
RSA module
====================================================

Module for calculating large primes, and RSA encryption, decryption, signing
and verification. Includes generating public and private keys.

**WARNING:** This implementation does not use compression of the cleartext input to
prevent repetitions, or other common security improvements. Use with care.

"""

from rsa.key import newkeys, PrivateKey, PublicKey
from rsa.pkcs1 import (
    encrypt,
    decrypt,
    sign,
    verify,
    DecryptionError,
    VerificationError,
    find_signature_hash,
    sign_hash,
    compute_hash,
)
