import SPI_DataStore as datastore


def _parse_hex_bytes(s, expected_len):
    s = s.strip()
    if not s:
        return None
    cleaned = s.replace(" ", "").replace(",", "")
    try:
        b = bytes.fromhex(cleaned)
    except Exception:
        return None
    if len(b) < expected_len:
        b = b + b"\0" * (expected_len - len(b))
    return b[:expected_len]


def read_emdata():
    """Read only the EMData record."""
    return datastore.read_record("EMData")


def edit_emdata(em):
    """Simple interactive editor for EMData only (minimal changes)."""
    print("Edit EMData (type '-' to keep current):")
    print(f"  gamename:    {em.get('gamename','')}")
    print(f"  players:     {em.get('players',1)}")
    print(f"  digits:      {em.get('digits',1)}")
    print(f"  multiplier:  {em.get('multiplier',0)}")
    print(f"  filtermasks: {em.get('filtermasks')[:16]}... (len {len(em.get('filtermasks',b''))})")
    print(f"  carrythresholds: {em.get('carrythresholds')[:16]}... (len {len(em.get('carrythresholds',b''))})")
    print(f"  sensorlevels: {em.get('sensorlevels',[0,0])}")

    v = input("gamename: ").strip()
    if v != "-":
        em["gamename"] = v[:40]

    v = input("players: ").strip()
    if v != "-":
        try:
            p = int(v, 0)
            em["players"] = max(1, min(4, p))
        except Exception:
            pass

    v = input("digits: ").strip()
    if v != "-":
        try:
            d = int(v, 0)
            em["digits"] = max(1, min(8, d))
        except Exception:
            pass

    v = input("multiplier: ").strip()
    if v != "-":
        try:
            em["multiplier"] = int(v, 0)
        except Exception:
            pass

    v = input("filtermasks (hex, up to 40 bytes): ").strip()
    if v != "-":
        parsed = _parse_hex_bytes(v, 40)
        if parsed is not None:
            em["filtermasks"] = parsed

    v = input("carrythresholds (hex, up to 32 bytes): ").strip()
    if v != "-":
        parsed = _parse_hex_bytes(v, 32)
        if parsed is not None:
            em["carrythresholds"] = parsed

    v = input("sensorlevels (two ints, comma separated): ").strip()
    if v != "-":
        parts = [p.strip() for p in v.split(",")]
        try:
            s0 = int(parts[0], 0) if len(parts) > 0 and parts[0] != "" else em.get("sensorlevels",[0,0])[0]
            s1 = int(parts[1], 0) if len(parts) > 1 and parts[1] != "" else em.get("sensorlevels",[0,0])[1]
            em["sensorlevels"] = [s0 & 0xFFFFFFFF, s1 & 0xFFFFFFFF]
        except Exception:
            pass

    return em


def write_emdata(em):
    """Write EMData back to storage."""
    datastore.write_record("EMData", em)


def main():
    em = read_emdata()
    updated = edit_emdata(em)
    write_emdata(updated)
    print("EMData updated.")


if __name__ == "__main__":
    main()
