"""Small helpers for protecting the WebSocket bearer token."""

import hashlib
import hmac
import re

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_MIN_TOKEN_LENGTH = 32


def hash_token(token: str) -> str:
    """Return the SHA-256 digest for a sufficiently long random token."""
    if len(token) < _MIN_TOKEN_LENGTH:
        raise ValueError(f"Token must contain at least {_MIN_TOKEN_LENGTH} characters.")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_valid_token_hash(token_hash: str) -> bool:
    """Check that a configured token digest is a lowercase SHA-256 hex string."""
    return _SHA256_HEX.fullmatch(token_hash) is not None


def verify_token(token: str, expected_hash: str) -> bool:
    """Verify a presented token without a timing-sensitive string comparison."""
    if not is_valid_token_hash(expected_hash) or len(token) < _MIN_TOKEN_LENGTH:
        return False
    return hmac.compare_digest(hash_token(token), expected_hash)
