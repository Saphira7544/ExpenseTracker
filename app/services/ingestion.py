from parsers.detector import detect_config
from parsers.generic_parser import GenericParser
from categorizers.rule_categorizer import rule_based_categorize
from categorizers.openAI import classify_transactions_batch
from legacy_db.db import create_db, insert_transactions
from app.core.config import settings
from app.services.transactions import attach_user_to_transactions


def parse_transactions(file_path: str):
    config = detect_config(file_path)
    bank_parser = GenericParser(config)
    return bank_parser.parse(file_path)

def categorize_transactions(transactions, user_id: int, run_llm: bool = True):
    rule_based_categorize(transactions, user_id)
    uncategorized = [t for t in transactions if not t.category]

    if run_llm and uncategorized:
        descriptions = [t.description for t in uncategorized]
        categories = classify_transactions_batch(descriptions)
        for t, cat in zip(uncategorized, categories):
            t.category = cat

    return {
        "rule_matched": len(transactions) - len(uncategorized),
        "llm_matched": len(uncategorized) if run_llm else 0,
    }

def process_uploaded_file(file_path: str, user_id: int, run_llm: bool = None) -> dict:
    run_llm = settings.ENABLE_LLM_CATEGORIZATION if run_llm is None else run_llm

    transactions = parse_transactions(file_path)
    attach_user_to_transactions(transactions, user_id)
    cat_stats = categorize_transactions(transactions, user_id=user_id, run_llm=run_llm)

    create_db()
    insert_transactions(transactions)

    return {
        "parsed": len(transactions),
        **cat_stats,
    }