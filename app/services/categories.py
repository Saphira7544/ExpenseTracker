"""The categories each user can pick: the built-in list (app/core/categories.py)
plus the ones they added on the Categories page.

Everything that offers or checks a category (dropdowns, rules, the AI
categorizer, dashboard roles, colours, Monthly Sheet groups) asks here, so a
new category works everywhere as soon as it's added: nothing to re-run.
"""
import re

from sqlalchemy import text

from app.core.categories import CATEGORIES, CATEGORY_COLORS, SHEET_GROUPS, SHEET_FALLBACK_GROUP
from app.db.session import engine

# Labels the app uses itself; never valid as a new category's name.
RESERVED = {"Uncategorized", "Split"}
MAX_NAME_LENGTH = 40
COLOR_PATTERN = re.compile(r"#[0-9a-f]{6}")

# Offered as the default colour for a new category: the first one not in use.
SUGGESTED_COLORS = [
    "#0f766e", "#b45309", "#be185d", "#4d7c0f", "#1e40af", "#9f1239",
    "#0369a1", "#6d28d9", "#a16207", "#047857", "#c2410c", "#475569",
]


def list_custom(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, name, color, sheet_group FROM custom_categories
            WHERE user_id = :user_id ORDER BY LOWER(name)
        """), {"user_id": user_id}).mappings().all()
    return [dict(r) for r in rows]


def categories_for(user_id: int, custom: list[dict] | None = None) -> list[str]:
    """Built-in categories, then the user's own, with Other (the catch-all) last."""
    custom = list_custom(user_id) if custom is None else custom
    built_in = [c for c in CATEGORIES if c != "Other"]
    return built_in + [c["name"] for c in custom] + ["Other"]


def colors_for(user_id: int | None) -> dict:
    if user_id is None:
        return dict(CATEGORY_COLORS)
    return {**CATEGORY_COLORS, **{c["name"]: c["color"] for c in list_custom(user_id)}}


def sheet_groups_for(user_id: int) -> list[dict]:
    """SHEET_GROUPS with each custom category added to the group it was given."""
    groups = [{**g, "categories": list(g["categories"])} for g in SHEET_GROUPS]
    by_name = {g["name"]: g for g in groups}
    for c in list_custom(user_id):
        by_name.get(c["sheet_group"], by_name[SHEET_FALLBACK_GROUP])["categories"].append(c["name"])
    return groups


def unknown_categories(user_id: int, values) -> list[str]:
    known = set(categories_for(user_id))
    return sorted({v for v in values if v not in known})


def suggest_color(user_id: int) -> str:
    used = {c.lower() for c in colors_for(user_id).values()}
    return next((c for c in SUGGESTED_COLORS if c not in used), SUGGESTED_COLORS[0])


def sheet_group_names() -> list[str]:
    return [g["name"] for g in SHEET_GROUPS]


def name_problem(user_id: int, name: str) -> str | None:
    if not name:
        return "Give the category a name"
    if len(name) > MAX_NAME_LENGTH:
        return f"Keep the name under {MAX_NAME_LENGTH} characters"
    taken = {c.lower() for c in categories_for(user_id)} | {r.lower() for r in RESERVED}
    if name.lower() in taken:
        return f"There's already a category called {name}"
    return None


def field_problem(color: str, sheet_group: str) -> str | None:
    if not COLOR_PATTERN.fullmatch(color):
        return "Pick a colour"
    if sheet_group not in sheet_group_names():
        return "Unknown Monthly Sheet group"
    return None


def add_category(user_id: int, name: str, color: str, sheet_group: str) -> dict:
    with engine.connect() as conn:
        new_id = conn.execute(text("""
            INSERT INTO custom_categories (user_id, name, color, sheet_group)
            VALUES (:user_id, :name, :color, :sheet_group) RETURNING id
        """), {"user_id": user_id, "name": name, "color": color, "sheet_group": sheet_group}).scalar()
        conn.commit()
    return {"id": new_id, "name": name, "color": color, "sheet_group": sheet_group}


def update_category(user_id: int, category_id: int, color: str, sheet_group: str) -> bool:
    with engine.connect() as conn:
        updated = conn.execute(text("""
            UPDATE custom_categories SET color = :color, sheet_group = :sheet_group
            WHERE id = :id AND user_id = :user_id
        """), {"id": category_id, "user_id": user_id, "color": color, "sheet_group": sheet_group}).rowcount
        conn.commit()
    return updated > 0


def usage(user_id: int, names: list[str]) -> dict[str, dict]:
    """How many transactions (or split parts), rules and dashboard roles use each category."""
    counts = {n: {"transactions": 0, "rules": 0, "roles": 0} for n in names}
    if not names:
        return counts
    with engine.connect() as conn:
        for key, sql in [
            ("transactions", """
                SELECT category, COUNT(*) FROM (
                    SELECT category FROM transactions WHERE user_id = :user_id
                    UNION ALL
                    SELECT category FROM transaction_splits WHERE user_id = :user_id
                ) t WHERE category = ANY(:names) GROUP BY category"""),
            ("rules", """
                SELECT category, COUNT(*) FROM category_rules
                WHERE user_id = :user_id AND category = ANY(:names) GROUP BY category"""),
            ("roles", """
                SELECT category, COUNT(*) FROM user_settings,
                    UNNEST(income_categories || investment_categories || ignored_categories) AS category
                WHERE user_id = :user_id AND category = ANY(:names) GROUP BY category"""),
        ]:
            for category, count in conn.execute(text(sql), {"user_id": user_id, "names": names}).all():
                counts[category][key] = int(count)
    return counts


def delete_category(user_id: int, category_id: int) -> str | None:
    """Delete one of the user's categories; refuses (returns why) while anything uses it."""
    match = [c for c in list_custom(user_id) if c["id"] == category_id]
    if not match:
        return "not found"
    name = match[0]["name"]
    used = usage(user_id, [name])[name]
    if any(used.values()):
        parts = [f"{n} {what}{'' if n == 1 else 's'}" for what, n in [
            ("transaction", used["transactions"]), ("rule", used["rules"]),
        ] if n]
        if used["roles"]:
            parts.append("the dashboard settings")
        return f"{name} is still used by {' and '.join(parts)}. Move those to another category first."
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM custom_categories WHERE id = :id AND user_id = :user_id"),
                     {"id": category_id, "user_id": user_id})
        conn.commit()
    return None
