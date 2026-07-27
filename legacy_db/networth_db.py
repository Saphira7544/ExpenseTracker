from sqlalchemy import text
from legacy_db.db import get_engine

def create_networth_tables():
    with get_engine().connect() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS networth_institutions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (user_id, name)
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS networth_asset_categories (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (user_id, name)
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS networth_account_types (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (user_id, name)
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS networth_currencies (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            code TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (user_id, code)
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS networth_liquidity_statuses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (user_id, name)
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS networth_accounts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            account_name TEXT NOT NULL,
            institution_id INTEGER REFERENCES networth_institutions(id),
            asset_category_id INTEGER REFERENCES networth_asset_categories(id),
            account_type_id INTEGER REFERENCES networth_account_types(id),
            currency_id INTEGER REFERENCES networth_currencies(id),
            liquidity_status_id INTEGER REFERENCES networth_liquidity_statuses(id),
            ticker_symbol TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS networth_valuations (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            account_id INTEGER NOT NULL REFERENCES networth_accounts(id) ON DELETE CASCADE,
            valuation_date DATE NOT NULL,
            quantity FLOAT,
            avg_purchase_price FLOAT,
            current_price FLOAT,
            current_value_original FLOAT,
            exchange_rate_to_chf FLOAT,
            current_value_chf FLOAT NOT NULL,
            source TEXT DEFAULT 'manual',
            note TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS networth_snapshots (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            snapshot_date DATE NOT NULL,
            total_liquid_chf FLOAT NOT NULL,
            total_illiquid_chf FLOAT NOT NULL,
            total_networth_chf FLOAT NOT NULL,
            mom_change_chf FLOAT,
            mom_change_pct FLOAT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (user_id, snapshot_date)
        )
        """))

        conn.commit()
        print("✅ Net worth tables ready")