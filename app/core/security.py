import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException

from app.core.config import settings


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    if not 1 <= len(plain.encode()) <= 72:
        raise ValueError("Password must contain between 1 and 72 UTF-8 bytes")
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False


def create_session_token(user_id: str, role: str, session_version: int = 0) -> str:
    """Create a signed JWT session token."""
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(UTC) + timedelta(seconds=settings.session_max_age),
        "iat": datetime.now(UTC),
        "jti": secrets.token_hex(16),
        "ver": session_version,
        "type": "session",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_session_token(token: str) -> dict:
    """Decode and verify a JWT session token. Raises HTTP 401 if invalid/expired."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "iat", "jti", "ver", "type"]},
        )
        if payload["type"] != "session" or not isinstance(payload["ver"], int):
            raise jwt.InvalidTokenError("Invalid session claims")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session token")


def generate_csrf_token(session_token: str = "") -> str:
    """Signed double-submit token, bound to the session (or anonymous login)."""
    nonce = secrets.token_hex(32)
    issued_at = str(int(time.time()))
    message = f"csrf:{nonce}:{issued_at}:{session_token}".encode()
    signature = hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()
    return f"{nonce}.{issued_at}.{signature}"


def verify_csrf_token(request_token: str, cookie_token: str, session_token: str = "") -> bool:
    """Check equality, signature, expiry and session binding; reject forged cookies."""
    try:
        if not hmac.compare_digest(request_token.encode(), cookie_token.encode()):
            return False
        nonce, issued_at, signature = cookie_token.split(".")
        age = time.time() - int(issued_at)
        if len(nonce) != 64 or not 0 <= age <= settings.csrf_token_expire:
            return False
        message = f"csrf:{nonce}:{issued_at}:{session_token}".encode()
        expected = hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature.encode(), expected.encode())
    except (ValueError, TypeError, UnicodeError):
        return False
