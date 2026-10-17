"""Password hashing and CSRF helpers (standard library only)."""

import hashlib
import hmac
import secrets

ALGO = "pbkdf2_sha256"
ITERATIONS = 260_000


def hash_password(password: str, iterations: int = ITERATIONS, salt_hex: str | None = None) -> str:
    """Return an encoded `pbkdf2_sha256$iterations$salt$hexdigest` string."""
    salt_hex = salt_hex or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations
    )
    return f"{ALGO}${iterations}${salt_hex}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iterations, salt_hex, expected = stored.split("$", 3)
        if algo != ALGO:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected)
    except Exception:
        return False


def new_token() -> str:
    """Random token used as the per-session CSRF token."""
    return secrets.token_urlsafe(32)
