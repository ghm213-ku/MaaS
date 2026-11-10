import os
import secrets
import jwt
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext

# Configuration
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    secret_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".jwt_secret")
    if os.path.exists(secret_path):
        with open(secret_path, "r") as f:
            JWT_SECRET = f.read().strip()
    else:
        JWT_SECRET = secrets.token_hex(32)  # 256-bit string
        with open(secret_path, "w") as f:
            f.write(JWT_SECRET)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 7 * 24 * 60 * 60  # 1 week (604800 s)

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed one."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a plain password using bcrypt."""
    return pwd_context.hash(password)

def create_access_token(user_id: int, role: str) -> str:
    """Create a new JWT token."""
    now = int(datetime.now(timezone.utc).timestamp())
    exp = now + ACCESS_TOKEN_EXPIRE_SECONDS
    
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": exp
    }
    
    encoded_jwt = jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises PyJWTError on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
