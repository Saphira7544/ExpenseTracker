RULES = {
    "Investments": ["interactive brokers", "ib llc"],
    "Groceries":   ["migros", "coop", "aldi", "lidl", "denner"],
    "Transport":   ["sbb", "shell", "bp", "esso", "galp"],
}


def rule_based_categorize(transactions) -> None:
    for t in transactions:
        text = t.description.lower()
        for category, keywords in RULES.items():
            if any(kw in text for kw in keywords):
                t.category = category
                break

