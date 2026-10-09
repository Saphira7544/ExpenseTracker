from sqlalchemy import text
from models.transaction import Transaction
from app.db.session import engine

def get_engine():
    # Used to build a brand-new engine (and connection pool) on every call.
    return engine

def _migrate_transactions_key(conn):
    """Move older databases from PRIMARY KEY (transactionId) to (user_id, transactionId).

    The old key was global, so two users importing the same bank transaction
    (or the same hash ID) collided and the second import was silently skipped.
    Idempotent: does nothing once the new key exists.
    """
    already = conn.execute(text("""
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'transactions'::regclass AND contype = 'p'
          AND pg_get_constraintdef(oid) = 'PRIMARY KEY (user_id, transactionid)'
    """)).first()
    if already:
        return

    orphans = conn.execute(text("SELECT COUNT(*) FROM transactions WHERE user_id IS NULL")).scalar()
    if orphans:
        raise RuntimeError(
            f"{orphans} transactions have no user_id; assign them to a user "
            "(UPDATE transactions SET user_id = <id> WHERE user_id IS NULL) before starting."
        )

    conn.execute(text("ALTER TABLE IF EXISTS transaction_splits DROP CONSTRAINT IF EXISTS transaction_splits_transactionid_fkey"))
    conn.execute(text("ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_pkey"))
    conn.execute(text("ALTER TABLE transactions ALTER COLUMN user_id SET NOT NULL"))
    conn.execute(text("ALTER TABLE transactions ADD PRIMARY KEY (user_id, transactionId)"))


def create_db():
    with get_engine().connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                transactionId TEXT NOT NULL,
                date DATE NOT NULL,
                transactionType TEXT NOT NULL,
                description TEXT,
                amount FLOAT NOT NULL,
                currency TEXT NOT NULL,
                account TEXT NOT NULL,
                sourceFile TEXT NOT NULL,
                category TEXT,
                is_manual_category BOOLEAN DEFAULT FALSE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                category_before_split TEXT,
                PRIMARY KEY (user_id, transactionId)
            )
        """))
        conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_before_split TEXT"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS transactions_user_date_idx ON transactions (user_id, date)"))
        _migrate_transactions_key(conn)
        conn.commit()
    print("✅ Table ready")

def create_splits_table():
    with get_engine().connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transaction_splits (
                id SERIAL PRIMARY KEY,
                transactionId TEXT NOT NULL,
                category TEXT NOT NULL,
                amount FLOAT NOT NULL,
                note TEXT,
                user_id INTEGER REFERENCES users(id)
            )
        """))
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'transaction_splits_txn_fk') THEN
                    ALTER TABLE transaction_splits
                        ADD CONSTRAINT transaction_splits_txn_fk
                        FOREIGN KEY (user_id, transactionId) REFERENCES transactions (user_id, transactionId);
                END IF;
            END $$;
        """))
        conn.commit()
    print("✅ Splits table ready")

def create_rules_table():
    with get_engine().connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS category_rules (
                id SERIAL PRIMARY KEY,
                category TEXT NOT NULL,
                keyword TEXT NOT NULL,
                user_id INTEGER REFERENCES users(id)
            )
        """))
        conn.commit()
    print("✅ Rules table ready")

def create_users_and_ownership():
    with get_engine().connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_approved BOOLEAN DEFAULT FALSE,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        # Bumped on password reset: sessions carry it, so older sessions stop working.
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 0"))
        # Password reset links: only a hash of the token is stored; single use, short-lived.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()
    print("✅ Users table ready")

def insert_transactions(transactions: list[Transaction]) -> set[str]:
    """Insert new transactions; returns the IDs actually inserted (existing ones are skipped)."""
    inserted_ids = set()
    skipped = 0
    with get_engine().connect() as conn:
        for t in transactions:
            result = conn.execute(text("""
                INSERT INTO transactions 
                (transactionId, date, transactionType, description, amount, currency, account, sourceFile, category, user_id)
                VALUES (:id, :date, :type, :desc, :amount, :currency, :account, :source, :category, :user_id)
                ON CONFLICT (user_id, transactionId) DO NOTHING
            """), {
                "id": t.transactionId,
                "date": t.date.date() if t.date else None,
                "type": t.transactionType.value,
                "desc": t.description,
                "amount": t.amount,
                "currency": t.currency,
                "account": t.account,
                "source": t.sourceFile,
                "category": t.category,
                "user_id": t.user_id
            })
            if result.rowcount > 0:
                inserted_ids.add(t.transactionId)
            else:
                skipped += 1
        conn.commit()
    print(f"✅ Inserted: {len(inserted_ids)} | Skipped (duplicates): {skipped}")
    return inserted_ids
