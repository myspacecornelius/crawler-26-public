"""
Authentication and authorization for the LeadFactory API.

- JWT-based auth with configurable token expiry
- Password hashing via passlib (bcrypt scheme)
- Password complexity enforcement
- API key generation and hashing
"""

import re
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .settings import settings

# ── Config ───────────────────────────────────────

SECRET_KEY = settings.secret_key
ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_HOURS = settings.access_token_expire_hours

security = HTTPBearer()

# ── Password hashing (passlib) ───────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt via passlib."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a hash."""
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def validate_password_complexity(password: str) -> Optional[str]:
    """Check password meets complexity requirements.

    Returns an error message if the password is too weak, or None if it passes.
    """
    if len(password) < settings.password_min_length:
        return f"Password must be at least {settings.password_min_length} characters"
    if settings.password_require_uppercase and not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter"
    if settings.password_require_digit and not re.search(r"\d", password):
        return "Password must contain at least one digit"
    if settings.password_require_special and not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "Password must contain at least one special character"
    return None


# ── JWT tokens ──────────────────────────────────

def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    """Decode JWT and return user_id, or None if invalid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# ── API key hashing ─────────────────────────────

def generate_api_key() -> tuple[str, str]:
    """Generate a new API key and its hash. Returns (raw_key, key_hash)."""
    raw_key = f"lf_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ── Dependency ──────────────────────────────────

async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """FastAPI dependency that extracts user_id from JWT bearer token."""
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
