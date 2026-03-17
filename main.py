import argparse
from parsers.generic_parser import GenericParser
from parsers.banks_configs import UBS_CONFIGS
from db.db import create_db, insert_transactions
from openAI.categorizer import classify_transactions_batch
# from parsers.cgd_parser import CGDParser  # Not implemented yet

def get_parser(bank: str):
    bank = bank.lower()
    if bank == "ubs":
        return GenericParser(UBS_CONFIGS)
    # elif bank == "cgd":
    #     return CGDParser()
    else:
        raise ValueError(f"No parser found for bank: {bank}")

def main():
    parser = argparse.ArgumentParser(description="Parse a bank CSV file into transactions.")
    parser.add_argument("--file", required=True, help="Path to the CSV file")
    parser.add_argument("--bank", required=True, help="Bank name (e.g., ubs)")
    parser.add_argument('--categorize', action='store_true', help='Run LLM categorization')
    args = parser.parse_args()

    # Parse
    bank_parser = get_parser(args.bank)
    transactions = bank_parser.parse(args.file)
    print(f"Parsed {len(transactions)} transactions from {args.file}")
    
    

    # Categorize (optional flag)
    if args.categorize:
        print(" Running LLM categorization...")
        descriptions = [t.description for t in transactions]
        categories = classify_transactions_batch(descriptions)
        for t, cat in zip(transactions, categories):
            t.category = cat
        print(" Categorization done")

    # DB 
    create_db()
    insert_transactions(transactions)
    
    for tx in transactions[:20]:
        print(tx)

if __name__ == "__main__":
    main()
