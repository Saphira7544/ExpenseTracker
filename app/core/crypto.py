"""Encrypts secrets kept in the database (e.g. a user's AI key), so a database
backup alone doesn't expose them. The encryption key is derived from
APP_SECRET_KEY: if that changes, stored secrets can no longer be read and have
to be saved again.
"""
import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings


def _fernet() -> Fernet:
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"expense-tracker:stored-secrets")
    return Fernet(base64.urlsafe_b64encode(derived.derive(settings.APP_SECRET_KEY.encode())))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str | None:
    """None when it can't be read (APP_SECRET_KEY changed, or the data is damaged)."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
