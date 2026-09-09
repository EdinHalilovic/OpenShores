

def _as_auid(val) -> int:
    if isinstance(val, int):
        return val & 0xFFFFFFFF
    if isinstance(val, (bytes, bytearray)):
        try:
            return int.from_bytes(bytes(val[:4]), "big")
        except Exception:
            return 0
    return 0
