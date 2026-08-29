def hamming_distance(hash1, hash2):
    if len(hash1) != len(hash2):
        raise ValueError("Hashes must have the same length")

    return sum(
        bit1 != bit2
        for bit1, bit2 in zip(hash1, hash2)
    )