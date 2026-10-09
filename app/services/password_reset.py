"""Forgot-password flow.

- A reset link carries a random 256-bit token; only its SHA-256 is stored, so the
  database alone can't be used to reset anyone's password.
- Links expire after RESET_TTL_MINUTES and work once. Asking again cancels older links.
- Resetting bumps the user's session_version, signing out every existing session.
- Whether the email exists is never revealed; the email is sent in the background
  so response times don't reveal it either.
"""
import hashlib
import logging
import secrets
import threading
from urllib.parse import quote

from sqlalchemy import text

from app.core.auth import hash_password
from app.core.config import settings
from app.db.session import engine
from app.services.email import email_configured, send_email

logger = logging.getLogger("uvicorn.error")

RESET_TTL_MINUTES = 30


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def reset_link(token: str) -> str:
    return f"{settings.APP_BASE_URL}/reset-password?token={quote(token)}"


def reset_email(link: str) -> tuple[str, str, str]:
    subject = "Reset your Expense Tracker password"
    text_body = (
        "Someone (hopefully you) asked to reset your Expense Tracker password.\n\n"
        f"Choose a new password here (the link works once, for {RESET_TTL_MINUTES} minutes):\n{link}\n\n"
        "If you didn't ask for this, ignore this email: your password stays the same."
    )
    html_body = f"""
      <p>Someone (hopefully you) asked to reset your Expense Tracker password.</p>
      <p><a href="{link}" style="display:inline-block;padding:10px 18px;background:#4f8ef7;color:#fff;
            border-radius:6px;text-decoration:none;font-weight:600;">Choose a new password</a></p>
      <p style="color:#64748b;font-size:13px;">The link works once, for {RESET_TTL_MINUTES} minutes.
         If you didn't ask for this, ignore this email: your password stays the same.</p>
    """
    return subject, text_body, html_body


def create_reset_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with engine.connect() as conn:
        # Only the newest link works.
        conn.execute(text("""
            UPDATE password_resets SET used_at = NOW()
            WHERE user_id = :user_id AND used_at IS NULL
        """), {"user_id": user_id})
        conn.execute(text("""
            INSERT INTO password_resets (user_id, token_hash, expires_at)
            VALUES (:user_id, :token_hash, NOW() + make_interval(mins => :ttl))
        """), {"user_id": user_id, "token_hash": hash_token(token), "ttl": RESET_TTL_MINUTES})
        conn.commit()
    return token


def _deliver(email: str, user_id: int) -> None:
    try:
        link = reset_link(create_reset_token(user_id))
        if email_configured():
            send_email(email, *reset_email(link))
            logger.info("Password reset email sent to %s", email)
        else:
            # No mail server configured (e.g. right after installing locally): the
            # link goes to the server log, which only someone at this PC can read.
            logger.warning("Email isn't configured (SMTP_HOST/SMTP_FROM in .env). "
                           "Password reset link for %s: %s", email, link)
    except Exception:
        logger.exception("Could not send the password reset email to %s", email)


def request_reset(email: str) -> None:
    """Fire-and-forget: same behaviour (and timing) whether or not the account exists."""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, email FROM users WHERE email = :email"),
                           {"email": email.lower().strip()}).first()
    if row:
        threading.Thread(target=_deliver, args=(row[1], row[0]), daemon=True).start()


def token_is_valid(token: str) -> bool:
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT 1 FROM password_resets
            WHERE token_hash = :token_hash AND used_at IS NULL AND expires_at > NOW()
        """), {"token_hash": hash_token(token)}).first() is not None


def reset_password(token: str, new_password: str) -> bool:
    """Set the new password if the token is valid. One statement marks the token used,
    so two simultaneous submissions can't both succeed."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            UPDATE password_resets SET used_at = NOW()
            WHERE token_hash = :token_hash AND used_at IS NULL AND expires_at > NOW()
            RETURNING user_id
        """), {"token_hash": hash_token(token)}).first()
        if not row:
            return False
        user_id = row[0]
        conn.execute(text("""
            UPDATE users SET password_hash = :password_hash, session_version = session_version + 1
            WHERE id = :user_id
        """), {"password_hash": hash_password(new_password), "user_id": user_id})
        conn.execute(text("""
            UPDATE password_resets SET used_at = NOW()
            WHERE user_id = :user_id AND used_at IS NULL
        """), {"user_id": user_id})
        conn.commit()
    return True
