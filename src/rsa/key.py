DEFAULT_EXPONENT = 65537


class PublicKey:
    """Represents a public RSA key.

    This key is also known as the 'encryption key'. It contains the 'n' and 'e'
    values.

    Supports attributes as well as dictionary-like access. Attribute access is
    faster, though.

    >>> PublicKey(5, 3)
    PublicKey(5, 3)

    >>> key = PublicKey(5, 3)
    >>> key.n
    5
    >>> key['n']
    5
    >>> key.e
    3
    >>> key['e']
    3

    """

    __slots__ = ("n", "e")

    def __init__(self, n: int, e: int) -> None:
        self.n = n
        self.e = e

    def __getitem__(self, key: str):
        return getattr(self, key)

    def __repr__(self) -> str:
        return "PublicKey(%i, %i)" % (self.n, self.e)

    def __getstate__(self):
        """Returns the key as tuple for pickling."""
        return self.n, self.e

    def __setstate__(self, state) -> None:
        """Sets the key from tuple."""
        self.n, self.e = state

    def __eq__(self, other) -> bool:
        if other is None:
            return False

        if not isinstance(other, PublicKey):
            return False

        return self.n == other.n and self.e == other.e

    def __ne__(self, other) -> bool:
        return not self == other

    def __hash__(self) -> int:
        return hash((self.n, self.e))


__all__ = ["PublicKey"]
