import os
from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

load_dotenv()

_INSECURE_SECRETS = {"", "change-this-in-production"}


def _require_secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value in _INSECURE_SECRETS:
        raise RuntimeError(
            f"{name} is not set (or still has the placeholder value). "
            f"Set it to a long random string, e.g. "
            f"`python -c \"import secrets; print(secrets.token_urlsafe(48))\"`."
        )
    return value


def _database_url() -> URL:
    # Railway (and most hosts) provide a single DATABASE_URL; fall back to the
    # individual DB_* variables. URL.create escapes special characters in the
    # password, which an f-string URL does not.
    raw = os.getenv("DATABASE_URL", "").strip()
    if raw:
        url = make_url(raw.replace("postgres://", "postgresql://", 1))
        return url.set(drivername="postgresql+psycopg2")

    missing = [v for v in ("DB_USER", "DB_HOST", "DB_PORT", "DB_NAME") if not os.getenv(v)]
    if missing:
        raise RuntimeError(f"Set DATABASE_URL or the database variables {', '.join(missing)}.")
    return URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_NAME"),
    )


class Settings:
    DATABASE_URL = _database_url()

    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "storage/uploads")
    
    # Signs the session cookie: must be set explicitly, never defaulted.
    APP_SECRET_KEY = _require_secret("APP_SECRET_KEY")
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "expense_tracker_session")
    SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_DAYS", "14")) * 24 * 3600
    # Browsers accept Secure cookies on http://localhost, so this can stay on locally.
    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"

    ENABLE_LLM_CATEGORIZATION = os.getenv("ENABLE_LLM_CATEGORIZATION", "true").lower() == "true"

settings = Settings()
