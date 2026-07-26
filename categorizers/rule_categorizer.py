from app.db.session import engine
from sqlalchemy import text

def _get_rules_from_db():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT category, keyword FROM category_rules")).mappings().all()
    return [dict(r) for r in rows]

def rule_based_categorize(transactions) -> None:
    rules = _get_rules_from_db()
    for t in transactions:
        text_lower = t.description.lower()
        for rule in rules:
            if rule["keyword"] in text_lower:
                t.category = rule["category"]
                break

