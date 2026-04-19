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
        inserted = 0
        skipped = 0
        for t in transactions:
            try:
                cursor.execute("""
                    INSERT INTO transactions (
                        transaction_id, date, transaction_type, description, 
                        amount, currency, account, source_file, category
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        t.sourceFile,
                        t.category                
                    )
                )
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"Error inserting {t.transactionId}: {e}")
        conn.commit()
        print(f" Inserted: {inserted} | Skipped (duplicates): {skipped}")
