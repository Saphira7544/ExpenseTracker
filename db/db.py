import sqlite3
from models.transaction import Transaction

DB_NAME = "transactions.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def create_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            account TEXT NOT NULL,
            source_file TEXT NOT NULL,
            transaction_type TEXT NOT NULL CHECK(transaction_type IN ('debit', 'credit', 'null'))
        );
        """)
        conn.commit()

def insert_transactions(transactions: list[Transaction]):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO transactions (date, description, amount, currency, account, source_file, transaction_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                t.date.strftime("%Y-%m-%d") if t.date else None,
                t.description,
                t.amount,
                t.currency,
                t.account,
                t.source_file,
                t.transaction_type.value
            ) for t in transactions
        ])
        conn.commit()
