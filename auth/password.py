from __future__ import annotations

import base64
import hashlib
import os
import secrets

PBKDF2_ITERATIONS = 390000


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> tuple[str, str, int]:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return base64.b64encode(salt).decode("ascii"), base64.b64encode(dk).decode("ascii"), iterations


def verify_password(
    password: str,
    *,
    salt_b64: str,
    hash_b64: str,
    iterations: int = PBKDF2_ITERATIONS,
) -> bool:
    try:
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(dk, expected)
