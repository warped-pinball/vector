import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from common.rsa_verify import verify_pkcs1v15_sha256


class RSAVerifyTests(unittest.TestCase):
    MESSAGE = b"test message"
    PUBLIC_N = int(
        "9232005158126183162870854487563160531535430052549144399998514241325323225410795491161776310741354214627711560203191688610495883691391838502741232144846341"
    )
    PUBLIC_E = 65537
    SIGNATURE = bytes.fromhex(
        "028d3092fa7788607794a313217f7cc105b05b4ff7991dac532fc2ebeede400bce5ce561ef940d37c3697f94e271f9c3150ec35d8be244b23aedd2397be26962"
    )

    def test_valid_signature(self):
        self.assertTrue(
            verify_pkcs1v15_sha256(
                self.MESSAGE,
                self.SIGNATURE,
                self.PUBLIC_N,
                self.PUBLIC_E,
            )
        )

    def test_detects_tampered_message(self):
        self.assertFalse(
            verify_pkcs1v15_sha256(
                self.MESSAGE + b"!",
                self.SIGNATURE,
                self.PUBLIC_N,
                self.PUBLIC_E,
            )
        )

    def test_detects_tampered_signature(self):
        bad_signature = bytearray(self.SIGNATURE)
        bad_signature[-1] ^= 0x01
        self.assertFalse(
            verify_pkcs1v15_sha256(
                self.MESSAGE,
                bytes(bad_signature),
                self.PUBLIC_N,
                self.PUBLIC_E,
            )
        )


if __name__ == "__main__":
    unittest.main()
