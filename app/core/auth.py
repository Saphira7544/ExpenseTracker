import bcrypt
from itsdangerous import URLSafeSerializer, BadSignature
from app.core.config import settings

serializer = URLSafeSerializer(settings.APP_SECRET_KEY, salt="auth-cookie")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )

def create_session_token(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})

def read_session_token(token: str) -> int | None:
    try:
        data = serializer.loads(token)
        return data.get("user_id")
    except BadSignature:
        return None
