from sqlalchemy import text
from app.db.session import engine

def get_transactions(account=None, category=None, search=None, date_from=None, date_to=None,
                      amount_sign=None, min_amount=None, max_amount=None, split_status=None,
                      limit=50, offset=0):
    query = "SELECT * FROM transactions WHERE 1=1"
    params = {}

    if account:
        query += " AND account = :account"
        params["account"] = account
    if category:
        query += " AND category = :category"
        params["category"] = category
    if search:
        query += " AND description ILIKE :search"
        params["search"] = f"%{search}%"
    if date_from:
        query += " AND date >= :date_from"
        params["date_from"] = date_from
    if date_to:
        query += " AND date <= :date_to"
        params["date_to"] = date_to
    if amount_sign == "positive":
        query += " AND amount > 0"
    elif amount_sign == "negative":
        query += " AND amount < 0"
    if min_amount is not None:
        query += " AND ABS(amount) >= :min_amount"
        params["min_amount"] = min_amount
    if max_amount is not None:
        query += " AND ABS(amount) <= :max_amount"
        params["max_amount"] = max_amount
    if split_status == "split":
        query += " AND category = 'Split'"
    elif split_status == "not_split":
        query += " AND (category IS NULL OR category != 'Split')"

    query += " ORDER BY date DESC, transactionId ASC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [dict(r) for r in rows]

def count_transactions(account=None, category=None, search=None, date_from=None, date_to=None,
                        amount_sign=None, min_amount=None, max_amount=None, split_status=None):
    query = "SELECT COUNT(*) FROM transactions WHERE 1=1"
    params = {}

    if account:
        query += " AND account = :account"
        params["account"] = account
    if category:
        query += " AND category = :category"
        params["category"] = category
    if search:
        query += " AND description ILIKE :search"
        params["search"] = f"%{search}%"
    if date_from:
        query += " AND date >= :date_from"
        params["date_from"] = date_from
    if date_to:
        query += " AND date <= :date_to"
        params["date_to"] = date_to
    if amount_sign == "positive":
        query += " AND amount > 0"
    elif amount_sign == "negative":
        query += " AND amount < 0"
    if min_amount is not None:
        query += " AND ABS(amount) >= :min_amount"
        params["min_amount"] = min_amount
    if max_amount is not None:
        query += " AND ABS(amount) <= :max_amount"
        params["max_amount"] = max_amount
    if split_status == "split":
        query += " AND category = 'Split'"
    elif split_status == "not_split":
        query += " AND (category IS NULL OR category != 'Split')"

    with engine.connect() as conn:
        result = conn.execute(text(query), params).scalar()
    return result

def get_categories():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT category FROM transactions WHERE category IS NOT NULL ORDER BY category")).all()
    return [r[0] for r in rows]

def get_accounts():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT account FROM transactions ORDER BY account")).all()
    return [r[0] for r in rows]

# Split-related functions
def get_transaction_by_id(transaction_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM transactions WHERE transactionId = :id"),
            {"id": transaction_id}
        ).mappings().first()
    return dict(row) if row else None

# Function to save splits for a specific transaction
def save_splits(transaction_id: str, splits: list[dict], remainder_category: str = "Other") -> None:
    original = get_transaction_by_id(transaction_id)
    total_amount = abs(original["amount"])
    allocated = sum(s["amount"] for s in splits)
    remainder = round(total_amount - allocated, 2)

    with engine.connect() as conn:
        for s in splits:
            conn.execute(
                text("""
                    INSERT INTO transaction_splits (transactionId, category, amount, note)
                    VALUES (:id, :category, :amount, :note)
                """),
                {"id": transaction_id, "category": s["category"], "amount": s["amount"], "note": s.get("note")}
            )

        if remainder > 0.01:
            conn.execute(
                text("""
                    INSERT INTO transaction_splits (transactionId, category, amount, note)
                    VALUES (:id, :category, :amount, :note)
                """),
                {"id": transaction_id, "category": remainder_category, "amount": remainder, "note": "Auto remainder"}
            )

        conn.execute(
            text("UPDATE transactions SET category = 'Split' WHERE transactionId = :id"),
            {"id": transaction_id}
        )
        conn.commit()

# Function to undo splits for a specific transaction
def undo_split(transaction_id: str) -> None:
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM transaction_splits WHERE transactionId = :id"),
            {"id": transaction_id}
        )
        conn.execute(
            text("UPDATE transactions SET category = NULL WHERE transactionId = :id"),
            {"id": transaction_id}
        )
        conn.commit()

# Function to get splits for a specific transaction
def get_splits_for_transaction(transaction_id: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM transaction_splits WHERE transactionId = :id"),
            {"id": transaction_id}
        ).mappings().all()
    return [dict(r) for r in rows]

# Normal category update function
def update_transaction_category(transaction_id: str, category: str) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE transactions SET category = :category, is_manual_category = TRUE WHERE transactionId = :id"),
            {"category": category, "id": transaction_id}
        )
        conn.commit()
        return result.rowcount > 0
    
# Bulk update function
def bulk_update_category(transaction_ids: list[str], category: str) -> int:
    if not transaction_ids:
        return 0
    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE transactions SET category = :category, is_manual_category = TRUE WHERE transactionId = ANY(:ids)"),
            {"category": category, "ids": transaction_ids}
        )
        conn.commit()
        return result.rowcount

# Function to revert a transaction's category to automatic categorization
def revert_to_auto(transaction_id: str) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE transactions SET is_manual_category = FALSE WHERE transactionId = :id"),
            {"id": transaction_id}
        )
        conn.commit()
        return result.rowcount > 0