import json
import logging
from openai import APIConnectionError, APIError, AuthenticationError, OpenAI, RateLimitError

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"

NO_KEY_MESSAGE = "No OpenAI key is set up. Add one in Settings > AI categorization."


def _out_of_credit(exc: Exception) -> bool:
    return isinstance(exc, APIError) and "insufficient_quota" in (exc.type, exc.code)


def error_message(exc: Exception) -> str:
    """What went wrong, for the person using the app. Our own wording, because
    OpenAI's can quote part of the key."""
    if isinstance(exc, AuthenticationError):
        return "OpenAI rejected the API key. Check it in Settings > AI categorization."
    if _out_of_credit(exc):
        return ("Your OpenAI account has no credits left. Add credits at "
                "platform.openai.com/settings/organization/billing.")
    if isinstance(exc, RateLimitError):
        return "OpenAI is limiting requests right now. Try again in a minute."
    if isinstance(exc, APIConnectionError):
        return "Couldn't reach OpenAI. Check your internet connection and try again."
    if isinstance(exc, APIError) and getattr(exc, "status_code", None):
        return f"OpenAI returned an error (status {exc.status_code}). Try again later."
    return f"The AI categorization failed unexpectedly ({type(exc).__name__}). Details are in logs/server.log."


def _will_keep_failing(exc: Exception) -> bool:
    return isinstance(exc, AuthenticationError) or _out_of_credit(exc)


def check_key(api_key: str) -> tuple[bool, str | None]:
    """Try the key with the smallest possible request (one word, no transaction
    data). Returns (usable or unknown, problem to show). Only a rejected key is
    False: anything else may be temporary."""
    try:
        OpenAI(api_key=api_key).chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": "Reply with OK."}], max_tokens=1,
        )
    except AuthenticationError as exc:
        return False, error_message(exc)
    except Exception as exc:
        logger.warning("Could not verify the OpenAI key: %s", type(exc).__name__)
        return True, error_message(exc)
    return True, None


# Structured output: the model must return {index, category} pairs and the
# category is constrained to the user's list, so answers can't drift out of
# alignment with the inputs or invent categories.
def response_format(categories: list[str]) -> dict:
    return {
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
                                "category": {"type": "string", "enum": categories},
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


def _classify_batch(client: OpenAI, batch: list[str], categories: list[str]) -> list[str | None]:
    prompt_lines = "\n".join(f"{j}. {desc}" for j, desc in enumerate(batch, start=1))
    prompt = (
        "You are a financial transaction categorizer.\n"
        f"Categorize each transaction into one of these categories: {', '.join(categories)}.\n"
        "Use Internal for moving money between the person's own accounts or currencies "
        "(e.g. top-ups, currency exchanges), not for payments to other people.\n"
        "Return one result per transaction, using its number as the index.\n\n"
        f"Transactions:\n{prompt_lines}"
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format=response_format(categories),
        max_tokens=40 * len(batch) + 100,
        temperature=0,
    )

    results: list[str | None] = [None] * len(batch)
    for item in json.loads(response.choices[0].message.content)["results"]:
        i = item.get("index", 0) - 1
        if 0 <= i < len(batch) and item.get("category") in categories:
            results[i] = item["category"]
    return results


def classify_transactions_batch(descriptions: list[str], categories: list[str], api_key: str | None,
                                batch_size: int = 40) -> tuple[list[str | None], str | None]:
    """
    Classify descriptions with the LLM. Returns a list the same length as the
    input, plus a message for the user if something went wrong (None if not).
    Entries the model skipped, or whole batches that failed, come back as None
    (left uncategorized) instead of failing the upload.
    """
    if not api_key:
        return [None] * len(descriptions), NO_KEY_MESSAGE

    client = OpenAI(api_key=api_key)
    results: list[str | None] = []
    problem = None
    for i in range(0, len(descriptions), batch_size):
        batch = descriptions[i:i + batch_size]
        try:
            results.extend(_classify_batch(client, batch, categories))
        except Exception as exc:
            logger.exception("LLM categorization failed for a batch of %d transactions", len(batch))
            problem = problem or error_message(exc)
            results.extend([None] * len(batch))
            if _will_keep_failing(exc):
                results.extend([None] * (len(descriptions) - len(results)))
                break
    return results, problem
