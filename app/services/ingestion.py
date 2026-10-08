from parsers.detector import detect_config
from parsers.generic_parser import GenericParser
from categorizers.rule_categorizer import rule_based_categorize
from categorizers.openAI import classify_transactions_batch
from legacy_db.db import insert_transactions
from app.core.config import settings
from app.services.transactions import attach_user_to_transactions
from app.services.settings import get_exclusion_patterns
from app.services.bank_formats import detection_configs


def parse_transactions(file_path: str, user_id: int):
    """Returns (transactions, number of rows skipped by the user's exclusions)."""
    config = detect_config(file_path, detection_configs(user_id))
    bank_parser = GenericParser(config, get_exclusion_patterns(user_id, config["bank"]))
    transactions = bank_parser.parse(file_path)
    return transactions, bank_parser.excluded_count

def categorize_transactions(transactions, user_id: int, run_llm: bool = True):
    rule_based_categorize(transactions, user_id)
    uncategorized = [t for t in transactions if not t.category]

    llm_matched = 0
    if run_llm and uncategorized:
        descriptions = [t.description for t in uncategorized]
        categories = classify_transactions_batch(descriptions)
        for t, cat in zip(uncategorized, categories):
            if cat:
                t.category = cat
                llm_matched += 1

    return {
        "rule_matched": len(transactions) - len(uncategorized),
        "llm_matched": llm_matched,
    }

def process_uploaded_file(file_path: str, user_id: int, run_llm: bool = None) -> dict:
    run_llm = settings.ENABLE_LLM_CATEGORIZATION if run_llm is None else run_llm

    transactions, excluded = parse_transactions(file_path, user_id)
    attach_user_to_transactions(transactions, user_id)
    cat_stats = categorize_transactions(transactions, user_id=user_id, run_llm=run_llm)

    insert_transactions(transactions)

    return {
        "parsed": len(transactions),
        "excluded": excluded,
        **cat_stats,
    }
