from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from models.transaction import Transaction
import os

load_dotenv()

def get_engine():
    url = (
        f"postgresql+psycopg2://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    return create_engine(url)

def create_db():
    with get_engine().connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                transactionId TEXT PRIMARY KEY,
                date DATE NOT NULL,
                transactionType TEXT NOT NULL,
                description TEXT,
                amount FLOAT NOT NULL,
                currency TEXT NOT NULL,
                account TEXT NOT NULL,
                sourceFile TEXT NOT NULL,
                category TEXT,
                is_manual_category BOOLEAN DEFAULT FALSE
            )   
        """))
        conn.commit()
        print("✅ Table ready")

def create_splits_table():
    with get_engine().connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transaction_splits (
                id SERIAL PRIMARY KEY,
                transactionId TEXT NOT NULL REFERENCES transactions(transactionId),
                category TEXT NOT NULL,
                amount FLOAT NOT NULL,
                note TEXT
            )
        """))
        conn.commit()
        print("✅ Splits table ready")

def create_rules_table():
    with get_engine().connect() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS category_rules (
            id SERIAL PRIMARY KEY,
            category TEXT NOT NULL,
            keyword TEXT NOT NULL
        )
        """))
        conn.commit()
        print("✅ Rules table ready")


def insert_transactions(transactions: list[Transaction]):
    inserted = 0
    skipped = 0
    with get_engine().connect() as conn:
        for t in transactions:
            result = conn.execute(text("""
                INSERT INTO transactions 
                (transactionId, date, transactionType, description, amount, currency, account, sourceFile, category)
                VALUES (:id, :date, :type, :desc, :amount, :currency, :account, :source, :category)
                ON CONFLICT (transactionId) DO NOTHING
            """), {
                "id": t.transactionId,
                "date": t.date.date() if t.date else None,
                "type": t.transactionType.value,
                "desc": t.description,
                "amount": t.amount,
                "currency": t.currency,
                "account": t.account,
                "source": t.sourceFile,
                "category": t.category
            })
            if result.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
    print(f"✅ Inserted: {inserted} | Skipped (duplicates): {skipped}")
