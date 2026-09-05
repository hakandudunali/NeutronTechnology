"""Cryptographic and mock authentication helpers."""

import hashlib
import hmac
import time
import uuid

import jwt
from fastapi import HTTPException, status

from app.core.config import settings


def verify_hmac_signature(signed_message: bytes, authorization_header: str) -> bool:
    """Verify the IoT HMAC-SHA256 Authorization header.

    The expected header format is `Bearer <hex_signature>` where the signature is
    HMAC-SHA256(secret_key, canonical_message). The canonical message is the
    concatenation `<rfid_uid><amount_2dp><timestamp>`, matching exactly what the
    Deneyap Kart firmware signs (see ekomatik_deneyap.ino: calculateHMAC()).
    The timestamp freshness check is performed separately because it is a
    semantic field in the JSON payload.
    """

    if not authorization_header.startswith("Bearer "):
        return False

    provided_signature = authorization_header[7:].strip().lower()
    expected_signature = hmac.new(
        settings.hmac_secret_key.encode("utf-8"), signed_message, hashlib.sha256
    ).hexdigest().lower()

    # compare_digest prevents simple timing side-channel comparisons.
    return hmac.compare_digest(provided_signature, expected_signature)


def verify_timestamp(timestamp: int) -> bool:
    """Return True only when an IoT timestamp is within the allowed time window.

    Both old and future-dated requests are rejected. This protects against replay
    attacks and also avoids accepting a forged request with a timestamp far in the future.
    """

    now = int(time.time())
    return abs(now - timestamp) <= settings.hmac_max_age_seconds


def get_mock_user_id(authorization_header: str) -> uuid.UUID:
    """Decode a development JWT and return the authenticated user's UUID.

    The mobile API expects a real JWT-shaped token signed with `jwt_secret_key`.
    In this mock-auth implementation, the JWT `sub` claim is simply the user's UUID.
    Replace this helper with the project's identity-provider verification in production.
    """

    if not authorization_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")

    token = authorization_header[7:].strip()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = uuid.UUID(str(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT token"
        ) from exc

    return user_id