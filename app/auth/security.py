"""Cryptographic helpers: PIN/password hashing and session token generation."""

import secrets
import bcrypt


# ---------------------------------------------------------------------------
# PIN / Password hashing (bcrypt, cost=12)
# ---------------------------------------------------------------------------

def hash_pin(pin: str) -> str:
    """Return a bcrypt hash of the given PIN string."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pin.encode('utf-8'), salt).decode('utf-8')


def verify_pin(pin: str, pin_hash: str) -> bool:
    """Check *pin* against a stored bcrypt *pin_hash*."""
    return bcrypt.checkpw(pin.encode('utf-8'), pin_hash.encode('utf-8'))


hash_password = hash_pin       # alias – same algorithm for researcher passwords
verify_password = verify_pin   # alias


# ---------------------------------------------------------------------------
# Patient number / PIN generation
# ---------------------------------------------------------------------------

def generate_pin(length: int = 4) -> str:
    """Generate a random numeric PIN of *length* digits (default 4)."""
    upper = 10 ** length
    return str(secrets.randbelow(upper)).zfill(length)


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------

def generate_session_token() -> str:
    """Generate a cryptographically secure URL-safe session token."""
    return secrets.token_urlsafe(32)
