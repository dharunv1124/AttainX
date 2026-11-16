"""
Security and password hashing utilities.
Uses bcrypt directly for salt and key generation.
Uses PyJWT for signed bearer tokens.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
import jwt

from app.config import settings
from app.db.models import UserRole
from app.schemas.auth import TokenPayload


def hash_password(password: str) -> str:
    """Hash plaintext password with salted bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(username: str, role: UserRole, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": username,
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_jwt = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenPayload]:
    """Decode and validate a signed JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        username: str = payload.get("sub")
        role_str: str = payload.get("role")
        if username is None or role_str is None:
            return None
        return TokenPayload(sub=username, role=UserRole(role_str), exp=payload.get("exp"))
    except jwt.PyJWTError:
        return None
