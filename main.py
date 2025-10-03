import argparse
from parsers.ubs_parser import UBSParser
from db.db import create_db, insert_transactions
from openAI.categorizer import classify_transactions_batch
# from parsers.cgd_parser import CGDParser  # Not implemented yet

def get_parser(bank: str):
    bank = bank.lower()
    if bank == "ubs":
        return UBSParser()
    # elif bank == "cgd":
    #     return CGDParser()
    else:
        raise ValueError(f"No parser found for bank: {bank}")

def main():
    parser = argparse.ArgumentParser(description="Parse a bank CSV file into transactions.")
    parser.add_argument("--file", required=True, help="Path to the CSV file")
    parser.add_argument("--bank", required=True, help="Bank name (e.g., ubs, cgd, revolut)")
    args = parser.parse_args()

    bank_parser = get_parser(args.bank)

    create_db()

    transactions = bank_parser.parse(args.file)

    # --- Categorize transactions ---
    descriptions = [t.description for t in transactions]
    categories = classify_transactions_batch(descriptions)
    for t, cat in zip(transactions, categories):
        t.category = cat

    insert_transactions(transactions)

    for tx in transactions[:20]:
        print(tx)

if __name__ == "__main__":
    main()
