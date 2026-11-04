"""The OpenAI key used for AI categorization: one saved by the user in Settings
(encrypted), otherwise OPENAI_API_KEY from .env.

The saved key only ever leaves this module towards OpenAI: the API reports
whether there is one, never the key or any part of it.
"""
from sqlalchemy import text

from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.db.session import engine

MIN_KEY_LENGTH = 20
MAX_KEY_LENGTH = 500


def key_problem(api_key: str) -> str | None:
    """Fixed messages only: never repeat what was pasted."""
    if not api_key:
        return "Paste a key first."
    if not MIN_KEY_LENGTH <= len(api_key) <= MAX_KEY_LENGTH or not api_key.isascii() or any(c.isspace() for c in api_key):
        return "That doesn't look like an API key. Copy it again from OpenAI, without spaces."
    return None


def _load(user_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT encrypted_key, updated_at FROM user_ai_keys WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).mappings().first()
    return dict(row) if row else None


def get_api_key(user_id: int) -> str | None:
    row = _load(user_id)
    saved = decrypt(row["encrypted_key"]) if row else None
    return saved or settings.OPENAI_API_KEY or None


def key_status(user_id: int) -> dict:
    """What Settings shows. source: "saved", "env" or None."""
    row = _load(user_id)
    readable = bool(row) and decrypt(row["encrypted_key"]) is not None
    source = "saved" if readable else ("env" if settings.OPENAI_API_KEY else None)
    return {
        "source": source,
        "saved_at": row["updated_at"].isoformat() if readable else None,
        "unreadable": bool(row) and not readable,  # APP_SECRET_KEY changed: save it again
    }


def save_api_key(user_id: int, api_key: str) -> None:
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO user_ai_keys (user_id, encrypted_key) VALUES (:user_id, :encrypted_key)
                ON CONFLICT (user_id) DO UPDATE SET encrypted_key = EXCLUDED.encrypted_key, updated_at = NOW()
            """),
            {"user_id": user_id, "encrypted_key": encrypt(api_key)},
        )
        conn.commit()


def delete_api_key(user_id: int) -> None:
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM user_ai_keys WHERE user_id = :user_id"), {"user_id": user_id})
        conn.commit()
