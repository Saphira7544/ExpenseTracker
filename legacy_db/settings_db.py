from sqlalchemy import text
from legacy_db.db import get_engine

def create_settings_tables():
    with get_engine().connect() as conn:
        # Per-user preferences; a missing row means "all defaults".
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                display_currency TEXT NOT NULL DEFAULT 'CHF',
                income_categories TEXT[] NOT NULL DEFAULT '{Salary}',
                investment_categories TEXT[] NOT NULL DEFAULT '{Investments}',
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # Description substrings skipped on import (internal transfers etc.).
        # bank NULL = applies to every bank.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS import_exclusions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                bank TEXT,
                pattern TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # Daily ECB reference rates, expressed as units of `currency` per 1 EUR.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fx_rates (
                currency TEXT NOT NULL,
                rate_date DATE NOT NULL,
                per_eur DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (currency, rate_date)
            )
        """))
        # How to read each bank's CSV export (edited on the Banks page).
        # config holds the parser settings (columns, separator, date format...).
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bank_formats (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                bank TEXT NOT NULL,
                file_type TEXT NOT NULL,
                config JSONB NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (user_id, bank, file_type)
            )
        """))

        # One-time data steps that already ran (see legacy_db/migrations.py).
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()
    print("✅ Settings and FX tables ready")
