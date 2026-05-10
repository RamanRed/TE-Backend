import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET", "default-secret-key-change-me")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440")) # 24 hours

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify a JWT access token."""
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # Check expiration if not handled by jwt.decode
        return decoded_token
    except jwt.PyJWTError:
        return None

def extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Extract the raw token from a Bearer Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or not parts[1]:
        return None
    return parts[1].strip()

def get_token_claims_from_bearer(authorization: Optional[str]) -> Optional[Dict[str, Any]]:
    """Decode a Bearer token and return its claims if valid."""
    token = extract_bearer_token(authorization)
    if not token:
        return None
    return decode_access_token(token)

def extract_user_id_from_token(token: str) -> Optional[str]:
    """Extract user_id (sub claim) from JWT token."""
    payload = decode_access_token(token)
    if payload:
        return payload.get("sub")
    return None
