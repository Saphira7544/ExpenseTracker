import os
from openai import OpenAI
from typing import List
import pandas as pd

CATEGORIES = [
    "Salary",
    "Investments",
    "Groceries",
    "Restaurants/Bars",
    "Transport",
    "Housing",
    "Rents",
    "Health",
    "Subscriptions",
    "Transfers",
    "Shopping",
    "Entertainment",
    "Education/Work",
    "Travel",
    "Other"
]

# Get API Key from Environment variables
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Please set the OPENAI_API_KEY environment variable.")

# Initiate OpenAI client
client = OpenAI(api_key=api_key)

def classify_transaction(description: str) -> str:
    """
    Classify a transaction description into one of the predefined categories using GPT-4o-mini.
    """
    prompt = f"""
    You are a financial transaction categorizer. 
    Categorize the following transaction into one of these categories: {', '.join(CATEGORIES)}.
    Respond with only the category name, nothing else.

    Transaction: "{description}"
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10,
        temperature=0
    )

    return response.choices[0].message.content.strip()


if __name__ == "__main__":
    #example_description = "Migros M Weinbergli Luzern CHE"
    example_description = "Tech'Firm Info. Systems Zuerich AG;Hofwiesenstrasse 349; 8050 Zuerich; CH salary payment Reason for payment: Salaire / Salary 2025.12 - PEREIRA CASTELO Isabel; Costs: Incoming SIC-payment; Transaction no. 9999353ZC5292219"
    category = classify_transaction(example_description)
    print(f"{example_description} → {category}")
    example_description = "Eggstein Immobilien AG;Matthofstrand 8; 6005 Luzern credit Reason for payment: RUECKVERGUETUNG ZU VIEL BEZAHLTER MIETZINS FUER DEN EH-PLATZ; Costs: Incoming SIC-payment; Transaction no. 9999168ZC6078638"
    category = classify_transaction(example_description)
    print(f"{example_description} → {category}")
    example_description = "Interactive Brokers LLC;One Pickwick Plaza; US Greenwich, Connecticut 06830 U20456445 / ISABEL CASTE; e-banking payment order Reason for payment: U20456445 / Isabel Castelo; Account no. IBAN: CH64 0023 0230 0576 8905 U; Costs: E-Banking domestic; Transaction no. 0174352TI8935538"
    category = classify_transaction(example_description)
    print(f"{example_description} → {category}")