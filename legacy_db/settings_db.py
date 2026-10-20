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
        # Categories left out of every dashboard total (own-account moves, currency exchanges).
        conn.execute(text("""
            ALTER TABLE user_settings
            ADD COLUMN IF NOT EXISTS ignored_categories TEXT[] NOT NULL DEFAULT '{Internal}'
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

        # Uploads waiting for review: parsed + categorized rows are kept here
        # between "preview" and "import" so confirming inserts exactly what was
        # shown (and the LLM isn't called twice). Stale ones are cleaned up.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS staged_imports (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                files JSONB NOT NULL,
                transactions JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # Categories the user added on the Categories page, on top of the
        # built-in list in app/core/categories.py. sheet_group = the Monthly
        # Sheet section it's shown in.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS custom_categories (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                color TEXT NOT NULL,
                sheet_group TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS custom_categories_user_name
            ON custom_categories (user_id, LOWER(name))
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
