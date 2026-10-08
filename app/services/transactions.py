import uuid
from sqlalchemy import text
from app.db.session import engine

def attach_user_to_transactions(transactions, user_id: int) -> None:
    for t in transactions:
        t.user_id = user_id

def _filter_clause(user_id, account=None, category=None, search=None, date_from=None, date_to=None,
                   amount_sign=None, min_amount=None, max_amount=None, split_status=None):
    """WHERE clause + params shared by the list and count queries."""
    where = "WHERE user_id = :user_id"
    params = {"user_id": user_id}

    if account:
        where += " AND account = :account"
        params["account"] = account
    if category:
        where += " AND category = :category"
        params["category"] = category
    if search:
        where += " AND description ILIKE :search"
        params["search"] = f"%{search}%"
    if date_from:
        where += " AND date >= :date_from"
        params["date_from"] = date_from
    if date_to:
        where += " AND date <= :date_to"
        params["date_to"] = date_to
    if amount_sign == "positive":
        where += " AND amount > 0"
    elif amount_sign == "negative":
        where += " AND amount < 0"
    if min_amount is not None:
        where += " AND ABS(amount) >= :min_amount"
        params["min_amount"] = min_amount
    if max_amount is not None:
        where += " AND ABS(amount) <= :max_amount"
        params["max_amount"] = max_amount
    if split_status == "split":
        where += " AND category = 'Split'"
    elif split_status == "not_split":
        where += " AND (category IS NULL OR category != 'Split')"

    return where, params

def get_transactions(user_id, account=None, category=None, search=None, date_from=None, date_to=None,
                      amount_sign=None, min_amount=None, max_amount=None, split_status=None,
                      limit=50, offset=0):
    where, params = _filter_clause(user_id, account, category, search, date_from, date_to,
                                   amount_sign, min_amount, max_amount, split_status)
    query = f"SELECT * FROM transactions {where} ORDER BY date DESC, transactionId ASC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [dict(r) for r in rows]

def count_transactions(user_id, account=None, category=None, search=None, date_from=None, date_to=None,
                        amount_sign=None, min_amount=None, max_amount=None, split_status=None):
    where, params = _filter_clause(user_id, account, category, search, date_from, date_to,
                                   amount_sign, min_amount, max_amount, split_status)
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM transactions {where}"), params).scalar()

def get_categories(user_id: int):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT category FROM transactions WHERE user_id = :user_id AND category IS NOT NULL ORDER BY category"), 
                            {"user_id": user_id}).all()
    return [r[0] for r in rows]

def get_accounts(user_id: int):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT account FROM transactions WHERE user_id = :user_id ORDER BY account"), 
                            {"user_id": user_id}).all()
    return [r[0] for r in rows]

def get_currencies(user_id: int):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT currency FROM transactions WHERE user_id = :user_id ORDER BY currency"),
                            {"user_id": user_id}).all()
    return [r[0] for r in rows]

# Creating, editing and deleting transactions (the add/edit dialog)

MANUAL_SOURCE = "manual"

def _transaction_type(amount: float) -> str:
    return "credit" if amount > 0 else "debit"

def split_edit_problem(existing: dict, fields: dict) -> str | None:
    """A split transaction's parts must keep adding up to its amount, so the
    amount (and its sign) can't change until the split is undone."""
    if existing["category"] == "Split" and abs(float(existing["amount"]) - fields["amount"]) > 0.005:
        return "This transaction is split; undo the split before changing its amount"
    return None

def create_transaction(user_id: int, fields: dict) -> str:
    transaction_id = f"manual-{uuid.uuid4().hex[:16]}"
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO transactions
                (transactionId, date, transactionType, description, amount, currency, account,
                 sourceFile, category, is_manual_category, user_id)
                VALUES (:id, :date, :type, :description, :amount, :currency, :account,
                        :source, :category, :is_manual, :user_id)
            """),
            {
                "id": transaction_id,
                "date": fields["date"],
                "type": _transaction_type(fields["amount"]),
                "description": fields["description"],
                "amount": fields["amount"],
                "currency": fields["currency"],
                "account": fields["account"],
                "source": MANUAL_SOURCE,
                "category": fields.get("category"),
                # A category picked by hand must survive rule re-runs.
                "is_manual": fields.get("category") is not None,
                "user_id": user_id,
            }
        )
        conn.commit()
    return transaction_id

def update_transaction(user_id: int, existing: dict, fields: dict) -> None:
    """Edit any transaction (imported ones too). The ID is unchanged, so
    re-uploading the original file won't duplicate or overwrite the edit."""
    is_split = existing["category"] == "Split"
    category = existing["category"] if is_split else fields.get("category")
    if category is None:
        is_manual = False                   # "Uncategorized": let rules decide again
    elif category != existing["category"]:
        is_manual = True                    # picked by hand: rule re-runs leave it alone
    else:
        is_manual = bool(existing["is_manual_category"])
    with engine.connect() as conn:
        conn.execute(
            text("""
                UPDATE transactions
                SET date = :date, transactionType = :type, description = :description,
                    amount = :amount, currency = :currency, account = :account,
                    category = :category,
                    is_manual_category = :is_manual
                WHERE transactionId = :id AND user_id = :user_id
            """),
            {
                "id": existing["transactionid"],
                "user_id": user_id,
                "date": fields["date"],
                "type": _transaction_type(fields["amount"]),
                "description": fields["description"],
                "amount": fields["amount"],
                "currency": fields["currency"],
                "account": fields["account"],
                "category": category,
                "is_manual": is_manual,
            }
        )
        conn.commit()

def delete_transaction(user_id: int, transaction_id: str) -> bool:
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM transaction_splits WHERE transactionId = :id AND user_id = :user_id"),
            {"id": transaction_id, "user_id": user_id}
        )
        result = conn.execute(
            text("DELETE FROM transactions WHERE transactionId = :id AND user_id = :user_id"),
            {"id": transaction_id, "user_id": user_id}
        )
        conn.commit()
        return result.rowcount > 0

# Split-related functions
def get_transaction_by_id(user_id: int, transaction_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM transactions WHERE transactionId = :id AND user_id = :user_id"),
            {"id": transaction_id, "user_id": user_id}
        ).mappings().first()
    return dict(row) if row else None

# Function to save splits for a specific transaction
def save_splits(user_id: int, transaction_id: str, splits: list[dict], remainder_category: str = "Other") -> None:
    original = get_transaction_by_id(user_id, transaction_id)
    if original is None:
        raise ValueError("Transaction not found")
    total_amount = abs(original["amount"])
    allocated = sum(s["amount"] for s in splits)
    remainder = round(total_amount - allocated, 2)

    with engine.connect() as conn:
        # Re-splitting replaces the previous split instead of stacking on it.
        conn.execute(
            text("DELETE FROM transaction_splits WHERE transactionId = :id AND user_id = :user_id"),
            {"id": transaction_id, "user_id": user_id}
        )
        for s in splits:
            conn.execute(
                text("""
                    INSERT INTO transaction_splits (transactionId, category, amount, note, user_id)
                    VALUES (:id, :category, :amount, :note, :user_id)
                """),
                {
                    "id": transaction_id, 
                    "category": s["category"], 
                    "amount": s["amount"], 
                    "note": s.get("note"), 
                    "user_id": user_id
                }
            )

        if remainder > 0.01:
            conn.execute(
                text("""
                    INSERT INTO transaction_splits (transactionId, category, amount, note, user_id)
                    VALUES (:id, :category, :amount, :note, :user_id)
                    """),
                {
                    "id": transaction_id,
                    "category": remainder_category,
                    "amount": remainder,
                    "note": "Auto remainder",
                    "user_id": user_id,
                }
            )

        conn.execute(
            text("""
                UPDATE transactions
                SET category_before_split = CASE
                        WHEN category IS DISTINCT FROM 'Split' THEN category
                        ELSE category_before_split
                    END,
                    category = 'Split'
                WHERE transactionId = :id AND user_id = :user_id
            """),
            {"id": transaction_id, "user_id": user_id}
        )
        conn.commit()

# Function to undo splits for a specific transaction
def undo_split(user_id: int, transaction_id: str) -> None:
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM transaction_splits WHERE transactionId = :id AND user_id = :user_id"),
            {"id": transaction_id, "user_id": user_id}
        )
        conn.execute(
            text("""
                UPDATE transactions
                SET category = category_before_split, category_before_split = NULL
                WHERE transactionId = :id AND user_id = :user_id AND category = 'Split'
            """),
            {"id": transaction_id, "user_id": user_id}
        )
        conn.commit()

# Function to get splits for a specific transaction
def get_splits_for_transaction(user_id: int, transaction_id: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM transaction_splits WHERE transactionId = :id AND user_id = :user_id"),
            {"id": transaction_id, "user_id": user_id}
        ).mappings().all()
    return [dict(r) for r in rows]

# Normal category update function
def update_transaction_category(user_id: int, transaction_id: str, category: str) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE transactions SET category = :category, is_manual_category = TRUE WHERE transactionId = :id AND user_id = :user_id AND category IS DISTINCT FROM 'Split'"),
            {"category": category, "id": transaction_id, "user_id": user_id}
        )
        conn.commit()
        return result.rowcount > 0
    
# Bulk update function
def bulk_update_category(user_id: int, transaction_ids: list[str], category: str) -> int:
    if not transaction_ids:
        return 0
    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE transactions SET category = :category, is_manual_category = TRUE WHERE transactionId = ANY(:ids) AND user_id = :user_id AND category IS DISTINCT FROM 'Split'"),
            {"category": category, "ids": transaction_ids, "user_id": user_id}
        )
        conn.commit()
        return result.rowcount

# Function to revert a transaction's category to automatic categorization
def revert_to_auto(user_id: int, transaction_id: str) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE transactions SET is_manual_category = FALSE WHERE transactionId = :id AND user_id = :user_id"),
            {"id": transaction_id, "user_id": user_id}
        )
        conn.commit()
        return result.rowcount > 0