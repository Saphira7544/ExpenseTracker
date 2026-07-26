from sqlalchemy import text
from app.db.session import engine

def get_rules(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM category_rules WHERE user_id = :user_id ORDER BY category, keyword"), {"user_id": user_id}).mappings().all()
    return [dict(r) for r in rows]

def add_rule(category: str, keyword: str, user_id: int) -> int:
    with engine.connect() as conn:
        result = conn.execute(
            text("INSERT INTO category_rules (category, keyword, user_id) VALUES (:c, :k, :user_id) RETURNING id"),
            {"c": category, "k": keyword.lower().strip(), "user_id": user_id}
        )
        conn.commit()
        return result.scalar()

def delete_rule(rule_id: int, user_id: int) -> bool:
    with engine.connect() as conn:
        result = conn.execute(text("DELETE FROM category_rules WHERE id = :id AND user_id = :user_id"), {"id": rule_id, "user_id": user_id})
        conn.commit()
        return result.rowcount > 0

def _match_category(description: str, rules: list[dict]) -> str | None:
    text_lower = description.lower()
    for rule in rules:
        if rule["keyword"] in text_lower:
            return rule["category"]
    return None

def preview_rule_rerun(user_id: int) -> list[dict]:
    rules = get_rules(user_id)
    with engine.connect() as conn:
        transactions = conn.execute(
            text("SELECT transactionId, description, category FROM transactions WHERE is_manual_category = FALSE AND user_id = :user_id"),
            {"user_id": user_id}
        ).mappings().all()

    affected = []
    for t in transactions:
        new_category = _match_category(t["description"], rules)
        if new_category and new_category != t["category"]:
            affected.append({
                "transactionId": t["transactionid"],
                "description": t["description"],
                "old_category": t["category"],
                "new_category": new_category,
            })
    return affected

def apply_rule_rerun(user_id: int) -> int:
    affected = preview_rule_rerun(user_id)
    with engine.connect() as conn:
        for row in affected:
            conn.execute(
                text("UPDATE transactions SET category = :cat WHERE transactionId = :id AND user_id = :user_id"),
                {"cat": row["new_category"], "id": row["transactionId"], "user_id": user_id}
            )
        conn.commit()
    return len(affected)