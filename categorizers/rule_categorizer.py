from app.services.rules import get_rules_for_matching, match_category

def rule_based_categorize(transactions, user_id: int) -> None:
    rules = get_rules_for_matching(user_id)
    for t in transactions:
        category = match_category(t.description, rules)
        if category:
            t.category = category
