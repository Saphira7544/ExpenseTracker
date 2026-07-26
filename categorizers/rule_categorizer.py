from app.db.session import engine
from sqlalchemy import text

def _get_rules_from_db(user_id: int):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT category, keyword FROM category_rules WHERE user_id = :user_id"), 
            {"user_id": user_id}
        ).mappings().all()
    return [dict(r) for r in rows]

def rule_based_categorize(transactions, user_id: int) -> None:
    rules = _get_rules_from_db(user_id)
    for t in transactions:
        text_lower = t.description.lower()
        for rule in rules:
            if rule["keyword"] in text_lower:
                t.category = rule["category"]
                break

