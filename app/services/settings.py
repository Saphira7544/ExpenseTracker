from sqlalchemy import text
from app.db.session import engine
from app.core.categories import CATEGORIES
from app.services import bank_formats

SUPPORTED_DISPLAY_CURRENCIES = ["CHF", "EUR"]

DEFAULT_SETTINGS = {
    "display_currency": "CHF",
    "income_categories": ["Salary"],
    "investment_categories": ["Investments"],
}

def available_banks(user_id: int) -> list[str]:
    return bank_formats.available_banks(user_id)

def get_settings(user_id: int) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT display_currency, income_categories, investment_categories
                FROM user_settings WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        ).mappings().first()
    return {**DEFAULT_SETTINGS, **(dict(row) if row else {})}

def validate_settings(settings: dict) -> str | None:
    if settings["display_currency"] not in SUPPORTED_DISPLAY_CURRENCIES:
        return f"Display currency must be one of {', '.join(SUPPORTED_DISPLAY_CURRENCIES)}"
    for key in ("income_categories", "investment_categories"):
        unknown = set(settings[key]) - set(CATEGORIES)
        if unknown:
            return f"Unknown categories: {', '.join(sorted(unknown))}"
    overlap = set(settings["income_categories"]) & set(settings["investment_categories"])
    if overlap:
        return f"A category can't be both income and investment: {', '.join(sorted(overlap))}"
    return None

def save_settings(user_id: int, settings: dict) -> None:
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO user_settings (user_id, display_currency, income_categories, investment_categories)
                VALUES (:user_id, :display_currency, :income_categories, :investment_categories)
                ON CONFLICT (user_id) DO UPDATE SET
                    display_currency = EXCLUDED.display_currency,
                    income_categories = EXCLUDED.income_categories,
                    investment_categories = EXCLUDED.investment_categories,
                    updated_at = NOW()
            """),
            {
                "user_id": user_id,
                "display_currency": settings["display_currency"],
                "income_categories": list(settings["income_categories"]),
                "investment_categories": list(settings["investment_categories"]),
            }
        )
        conn.commit()

# Import exclusions

def list_exclusions(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, bank, pattern FROM import_exclusions
                WHERE user_id = :user_id
                ORDER BY bank NULLS FIRST, LOWER(pattern)
            """),
            {"user_id": user_id}
        ).mappings().all()
    return [dict(r) for r in rows]

def get_exclusion_patterns(user_id: int, bank: str) -> list[str]:
    """Patterns applied when importing a file from `bank` (bank-specific + all-bank ones)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT pattern FROM import_exclusions
                WHERE user_id = :user_id AND (bank IS NULL OR bank = :bank)
            """),
            {"user_id": user_id, "bank": bank}
        ).all()
    return [r[0] for r in rows]

def add_exclusion(user_id: int, bank: str | None, pattern: str) -> int:
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO import_exclusions (user_id, bank, pattern)
                VALUES (:user_id, :bank, :pattern)
                RETURNING id
            """),
            {"user_id": user_id, "bank": bank, "pattern": pattern.strip()}
        )
        conn.commit()
        return result.scalar()

def delete_exclusion(user_id: int, exclusion_id: int) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text("DELETE FROM import_exclusions WHERE id = :id AND user_id = :user_id"),
            {"id": exclusion_id, "user_id": user_id}
        )
        conn.commit()
        return result.rowcount > 0
