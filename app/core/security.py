import hmac
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException

from app.core.config import settings


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_session_token(user_id: str, role: str) -> str:
    """Create a signed JWT session token."""
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(UTC) + timedelta(seconds=settings.session_max_age),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_session_token(token: str) -> dict:
    """Decode and verify a JWT session token. Raises HTTP 401 if invalid/expired."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session token")


def generate_csrf_token() -> str:
    """Generate a random CSRF token."""
    return secrets.token_hex(32)


def verify_csrf_token(request_token: str, session_token: str) -> bool:
    """Compare CSRF tokens in constant time to prevent timing attacks."""
    return hmac.compare_digest(request_token, session_token)
