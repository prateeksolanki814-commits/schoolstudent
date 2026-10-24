"""Password hashing and validation using only Python's standard library."""
from __future__ import annotations

import hashlib
import hmac
import secrets

ITERATIONS = 310_000


def validate_password(password: str) -> str | None:
    if not isinstance(password, str) or len(password) < 10:
        return "Use a password with at least 10 characters."
    if password.strip() != password:
        return "Password cannot begin or end with spaces."
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        return "Include at least one letter and one number."
    return None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False
