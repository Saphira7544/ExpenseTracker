import argparse
from dotenv import load_dotenv

from parsers.detector import detect_config
from parsers.generic_parser import GenericParser
from db.db import create_db, insert_transactions
from openAI.categorizer import classify_transactions_batch

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Parse a bank CSV file into transactions.")
    parser.add_argument("--file", required=True, help="Path to the CSV file")
    parser.add_argument("--categorize", action="store_true", help="Run LLM categorization")
    args = parser.parse_args()

    # Parse
    config = detect_config(args.file)
    bank_parser = GenericParser(config)    
    transactions = bank_parser.parse(args.file)

    print(f"Parsed {len(transactions)} transactions from {args.file}")
    print(f"Detected bank={config['bank']} file_type={config['file_type']}")
    

    # Categorize (optional flag)
    if args.categorize:
        descriptions = [t.description for t in transactions]
        categories = classify_transactions_batch(descriptions)
        for t, cat in zip(transactions, categories):
            t.category = cat
        print(" Categorization done")

    # DB 
    create_db()
    insert_transactions(transactions)
    
    for tx in transactions[:10]:
        print(tx)

if __name__ == "__main__":
    main()
