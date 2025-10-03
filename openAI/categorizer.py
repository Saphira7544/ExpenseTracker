from openai import OpenAI

client = OpenAI()

CATEGORIES = [
    "Groceries",
    "Restaurants/Bars",
    "Transport",
    "Housing",
    "Health",
    "Subscriptions",
    "Transfers",
    "Shopping",
    "Entertainment",
    "Education/Work",
    "Travel"
    "Other"
]

def classify_transactions_batch(descriptions, batch_size=50):
    """
    Classify multiple transaction descriptions using GPT-4o-mini in batches.
    """
    results = []
    for i in range(0, len(descriptions), batch_size):
        batch = descriptions[i:i+batch_size]
        prompt_lines = [f"{j+1}. {desc}" for j, desc in enumerate(batch)]
       
        prompt = f"""
        You are a financial transaction categorizer.
        Categorize the following transactions into one of these categories: {', '.join(CATEGORIES)}.
        Respond with a numbered list matching the input, one category per transaction.

        Transactions:
        {'\n'.join(prompt_lines)}
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0
        )

        text = response.choices[0].message.content.strip()
        lines = text.splitlines()
        for line in lines:
            if "." in line:
                category = line.split(".", 1)[1].strip()
            else:
                category = line.strip()
            results.append(category)

    return results
