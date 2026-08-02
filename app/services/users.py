from sqlalchemy import text
from app.db.session import engine
from app.core.auth import hash_password, verify_password

def create_user(email: str, password: str) -> int:
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO users (email, password_hash)
                VALUES (:email, :password_hash)
                RETURNING id
            """),
            {"email": email.lower().strip(), "password_hash": hash_password(password)}
        )
        user_id = result.scalar()
        conn.commit()
        return user_id

def get_user_by_email(email: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM users WHERE email = :email"),
            {"email": email.lower().strip()}
        ).mappings().first()
    return dict(row) if row else None

def get_user_by_id(user_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM users WHERE id = :id"),
            {"id": user_id}
        ).mappings().first()
    return dict(row) if row else None

def authenticate_user(email: str, password: str) -> dict | None:
    user = get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user

