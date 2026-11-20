from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime


def github_signature_valid(secret: str, body: bytes, signature: str) -> bool:
    if not secret or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def signed_payload_valid(
    secret: str,
    body: bytes,
    signature: str,
    timestamp: str,
    tolerance_seconds: int = 300,
) -> bool:
    if not secret or not timestamp or not signature:
        return False
    try:
        signed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if signed_at.tzinfo is None:
        return False
    age = abs((datetime.now(UTC) - signed_at.astimezone(UTC)).total_seconds())
    if age > tolerance_seconds:
        return False
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def token_valid(expected: str, supplied: str) -> bool:
    return bool(expected) and hmac.compare_digest(expected, supplied)
