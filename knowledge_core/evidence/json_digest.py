"""Historical evidence hashing, distinct from the integer-only M0 asset format."""
import hashlib
import json


def evidence_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()
