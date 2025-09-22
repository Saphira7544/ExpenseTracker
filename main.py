import argparse
from parsers.ubs_parser import UBSParser
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
    transactions = bank_parser.parse(args.file)

    #for tx in transactions[:20]:
       # print(tx)

if __name__ == "__main__":
    main()
