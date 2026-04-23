# main.py

import argparse
from dotenv import load_dotenv

from parsers.detector import detect_config
from parsers.generic_parser import GenericParser
from db.db import create_db, insert_transactions
from categorizers.openAI import classify_transactions_batch
from categorizers.rule_categorizer import rule_based_categorize

load_dotenv()


def parse_transactions(file_path: str):
    config = detect_config(file_path)
    bank_parser = GenericParser(config)
    transactions = bank_parser.parse(file_path)
    print(f"Parsed {len(transactions)} transactions from {file_path}")
    print(f"Detected bank={config['bank']} file_type={config['file_type']}")
    return transactions


def categorize_transactions(transactions):
    rule_based_categorize(transactions)

    uncategorized = [t for t in transactions if not t.category]
    if uncategorized:
        descriptions = [t.description for t in uncategorized]
        categories = classify_transactions_batch(descriptions)
        for t, cat in zip(uncategorized, categories):
            t.category = cat

    print(f"Categorization done ({len(transactions) - len(uncategorized)} rules, {len(uncategorized)} LLM)")


def save_transactions(transactions):
    create_db()
    insert_transactions(transactions)


def main():
    parser = argparse.ArgumentParser(description="Parse a bank CSV file into transactions.")
    parser.add_argument("--file", required=True, help="Path to the CSV file")
    parser.add_argument("--categorize", action="store_true", help="Run LLM categorization")
    args = parser.parse_args()

    transactions = parse_transactions(args.file)

    if args.categorize:
        categorize_transactions(transactions)

    save_transactions(transactions)

    for tx in transactions[:10]:
        print(tx)


if __name__ == "__main__":
    main()
