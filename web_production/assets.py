"""Frozen V1.5 asset check, independent of the historical M1 evidence viewer."""
import hashlib

BASELINE_SHA = "a12cf30a5771b59cd9fabb00ea67d1bc84361d2a73c916c354593b1adc15eb80"


def checked(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("EVIDENCE_DIGEST_MISMATCH: " + path.name)
    return data
