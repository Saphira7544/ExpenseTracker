from sqlalchemy import text
from app.db.session import engine
from app.core.auth import hash_password, verify_password
from app.services.bank_formats import seed_default_formats

# Columns that are safe to hand to routes and templates (no password_hash).
PUBLIC_COLUMNS = "id, email, is_approved, is_admin, created_at"

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
        # New users start with the built-in bank formats (editable on the Banks page).
        seed_default_formats(conn, user_id)
        conn.execute(
            text("INSERT INTO schema_migrations (name) VALUES (:name) ON CONFLICT DO NOTHING"),
            {"name": f"seed_bank_formats:user:{user_id}"}
        )
        conn.commit()
        return user_id

def get_user_by_email(email: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {PUBLIC_COLUMNS} FROM users WHERE email = :email"),
            {"email": email.lower().strip()}
        ).mappings().first()
    return dict(row) if row else None

def get_user_by_id(user_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {PUBLIC_COLUMNS} FROM users WHERE id = :id"),
            {"id": user_id}
        ).mappings().first()
    return dict(row) if row else None

def authenticate_user(email: str, password: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {PUBLIC_COLUMNS}, password_hash FROM users WHERE email = :email"),
            {"email": email.lower().strip()}
        ).mappings().first()
    if not row or not verify_password(password, row["password_hash"]):
        return None
    user = dict(row)
    del user["password_hash"]
    return user

def list_pending_users() -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, email, created_at FROM users WHERE is_approved = FALSE ORDER BY created_at")
        ).mappings().all()
    return [dict(r) for r in rows]

def set_user_approved(user_id: int, approved: bool) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE users SET is_approved = :approved WHERE id = :id"),
            {"approved": approved, "id": user_id}
        )
        conn.commit()
        return result.rowcount > 0
