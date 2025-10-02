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
            transaction_id TEXT UNIQUE NOT NULL,
            date TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            account TEXT NOT NULL,
            source_file TEXT NOT NULL,
            category TEXT
        );
        """)
        conn.commit()

def insert_transactions(transactions: list[Transaction]):
    with get_connection() as conn:
        cursor = conn.cursor()
        for t in transactions:
            cursor.execute("""
                INSERT INTO transactions (
                    transaction_id, date, transaction_type, description, 
                    amount, currency, account, source_file
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(transaction_id) DO NOTHING;
            """, 
                (
                    t.transactionId,
                    t.date.isoformat() if t.date else None,
                    t.transactionType.value,
                    t.description,
                    t.amount,
                    t.currency,
                    t.account,
                    t.sourceFile                
                )
            )
        conn.commit()
