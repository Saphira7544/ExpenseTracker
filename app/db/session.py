# app/db/session.py
from sqlalchemy import create_engine
from app.core.config import settings

# The single connection pool for the whole app (legacy_db reuses it too).
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
