"""Turn face embeddings into 256-bit similarity-preserving fingerprints."""

import numpy as np


SIMHASH_BITS = 256
SIMHASH_SEED = 67


def generate_face_hash(embedding) -> str:
    """Return a deterministic 256-bit SimHash as 64 lowercase hex chars."""
    if embedding is None:
        raise ValueError("Embedding cannot be None.")

    vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
    if vector.size == 0 or not np.isfinite(vector).all():
        raise ValueError("Embedding must contain finite numeric values.")

    # The fixed seed makes the projection stable between enrollment and
    # verification while keeping the fingerprint independent of user_id.
    rng = np.random.default_rng(SIMHASH_SEED)
    projections = rng.standard_normal((SIMHASH_BITS, vector.size), dtype=np.float32)
    bits = projections @ vector >= 0

    fingerprint = 0
    for bit in bits:
        fingerprint = (fingerprint << 1) | int(bit)

    return format(fingerprint, "064x")
