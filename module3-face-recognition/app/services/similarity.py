SIMHASH_HEX_LENGTH = 64


def hamming_distance(hash1: str, hash2: str) -> int:
    """Return the bit-level Hamming distance between two 256-bit hex values."""
    if len(hash1) != SIMHASH_HEX_LENGTH or len(hash2) != SIMHASH_HEX_LENGTH:
        raise ValueError("SimHashes must be 64-character hexadecimal strings.")

    try:
        return (int(hash1, 16) ^ int(hash2, 16)).bit_count()
    except ValueError as exc:
        raise ValueError("SimHashes must contain only hexadecimal characters.") from exc
