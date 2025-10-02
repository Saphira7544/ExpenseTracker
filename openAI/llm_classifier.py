import os
from openai import OpenAI

CATEGORIES = [
    "Groceries",
    "Restaurants",
    "Transport",
    "Housing",
    "Health",
    "Subscriptions",
    "Transfers",
    "Shopping",
    "Entertainment",
    "Education/Work",
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
    example_description = "5402 - www.jumbo.ch      B�lach       CHE"
    example_description = "Asiaway AG               Luzern       CHE"
    example_description = "Avia Tankstelle          Rothenburg   CHE"
    category = classify_transaction(example_description)
    print(f"{example_description} → {category}")