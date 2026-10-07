import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature
from app.core.config import settings

# Timed so a stolen or forgotten cookie stops working after SESSION_MAX_AGE_SECONDS.
serializer = URLSafeTimedSerializer(settings.APP_SECRET_KEY, salt="auth-cookie")

# bcrypt only looks at the first 72 bytes and bcrypt>=5 raises beyond that.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8

def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"Password must be at most {MAX_PASSWORD_BYTES} bytes"
    return None

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8")
        )
    except ValueError:
        return False

def create_session_token(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})

def read_session_token(token: str) -> int | None:
    try:
        data = serializer.loads(token, max_age=settings.SESSION_MAX_AGE_SECONDS)
        return data.get("user_id")
    except BadSignature:  # also covers SignatureExpired
        return None
