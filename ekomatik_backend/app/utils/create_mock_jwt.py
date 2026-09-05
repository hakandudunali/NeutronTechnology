"""Command-line helper for generating a development JWT for a user UUID."""

import sys
import uuid

import jwt

from app.core.config import settings


def create_mock_jwt(user_id: uuid.UUID) -> str:
    """Create an HS256 JWT whose `sub` claim is the supplied user UUID."""

    payload = {"sub": str(user_id)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.utils.create_mock_jwt <user-uuid>")
    print(create_mock_jwt(uuid.UUID(sys.argv[1])))