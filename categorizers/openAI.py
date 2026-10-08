import json
import logging
from openai import OpenAI
from app.core.categories import CATEGORIES

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"

_client = None


def _get_client() -> OpenAI:
    # Created lazily so the app can start without OPENAI_API_KEY when LLM
    # categorization is disabled.
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


# Structured output: the model must return {index, category} pairs and the
# category is constrained to our list, so answers can't drift out of
# alignment with the inputs or invent categories.
RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "transaction_categories",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "category": {"type": "string", "enum": CATEGORIES},
                        },
                        "required": ["index", "category"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["results"],
            "additionalProperties": False,
        },
    },
}


def _classify_batch(batch: list[str]) -> list[str | None]:
    prompt_lines = "\n".join(f"{j}. {desc}" for j, desc in enumerate(batch, start=1))
    prompt = (
        "You are a financial transaction categorizer.\n"
        f"Categorize each transaction into one of these categories: {', '.join(CATEGORIES)}.\n"
        "Use Internal for moving money between the person's own accounts or currencies "
        "(e.g. top-ups, currency exchanges), not for payments to other people.\n"
        "Return one result per transaction, using its number as the index.\n\n"
        f"Transactions:\n{prompt_lines}"
    )

    response = _get_client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format=RESPONSE_FORMAT,
        max_tokens=40 * len(batch) + 100,
        temperature=0,
    )

    results: list[str | None] = [None] * len(batch)
    for item in json.loads(response.choices[0].message.content)["results"]:
        i = item.get("index", 0) - 1
        if 0 <= i < len(batch) and item.get("category") in CATEGORIES:
            results[i] = item["category"]
    return results


def classify_transactions_batch(descriptions: list[str], batch_size: int = 40) -> list[str | None]:
    """
    Classify descriptions with the LLM. Always returns a list the same length
    as the input; entries the model skipped, or whole batches that failed,
    come back as None (left uncategorized) instead of failing the upload.
    """
    results: list[str | None] = []
    for i in range(0, len(descriptions), batch_size):
        batch = descriptions[i:i + batch_size]
        try:
            results.extend(_classify_batch(batch))
        except Exception:
            logger.exception("LLM categorization failed for a batch of %d transactions", len(batch))
            results.extend([None] * len(batch))
    return results
