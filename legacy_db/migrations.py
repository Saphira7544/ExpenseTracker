"""One-time data steps, run at startup. Each step is recorded in schema_migrations
(per user where relevant) so it never runs twice; e.g. exclusions you delete
on the Settings page don't come back on the next restart."""
from sqlalchemy import text

from legacy_db.db import get_engine
from app.services.bank_formats import seed_default_formats

# The import exclusions that used to be hard-coded for UBS in parsers/bank_configs.py,
# before they became per-user settings. Restored only for admin accounts: the name
# pattern is the owner's own, and for anyone else it would hide real transfers.
LEGACY_UBS_EXCLUSIONS = [
    "Revolut",                  # Revolut top-ups (any account)
    "I. PEREIRA CASTELO",       # transfers between the owner's own accounts
    "Payment to card",          # debit account -> prepaid card
    "TRANSFER FROM ACCOUNT",    # prepaid card <- debit account
]


def _once(conn, name: str) -> bool:
    """Record `name` as applied; False if it already was."""
    return conn.execute(
        text("INSERT INTO schema_migrations (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"),
        {"name": name}
    ).rowcount > 0


def run_data_migrations():
    with get_engine().connect() as conn:
        user_ids = [r[0] for r in conn.execute(text("SELECT id FROM users ORDER BY id")).all()]

        # Every user starts with the built-in bank formats (new users get them on registration).
        for user_id in user_ids:
            if _once(conn, f"seed_bank_formats:user:{user_id}"):
                seed_default_formats(conn, user_id)

        # Restore the old hard-coded UBS exclusions for admins who import UBS files.
        admins_with_ubs = conn.execute(text("""
            SELECT DISTINCT u.id FROM users u JOIN transactions t ON t.user_id = u.id
            WHERE u.is_admin AND t.account ILIKE 'UBS%'
        """)).all()
        for (user_id,) in admins_with_ubs:
            if _once(conn, f"seed_legacy_ubs_exclusions:user:{user_id}"):
                for pattern in LEGACY_UBS_EXCLUSIONS:
                    conn.execute(text("""
                        INSERT INTO import_exclusions (user_id, bank, pattern)
                        SELECT :user_id, 'ubs', :pattern
                        WHERE NOT EXISTS (
                            SELECT 1 FROM import_exclusions
                            WHERE user_id = :user_id AND LOWER(pattern) = LOWER(:pattern)
                        )
                    """), {"user_id": user_id, "pattern": pattern})

        conn.commit()
    print("✅ Data migrations done")
