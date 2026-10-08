"""Bank file formats: how to read each bank's CSV export, configured per user on the Banks page.

A format's `config` is the dict GenericParser understands:
    bank, file_type, account, header (signature texts), sep, encoding,
    date_col, date_format, desc_cols, debit_col + credit_col *or* amount_col
    (+ invert_amount), currency_col *or* fixed_currency, id_col, decimal_sep,
    drop_empty_amount
"""
import json

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import engine
from parsers.detector import default_formats

CONFIG_KEYS = [
    "bank", "file_type", "account", "header", "sep", "encoding", "date_col", "date_format",
    "desc_cols", "debit_col", "credit_col", "amount_col", "invert_amount", "currency_col",
    "fixed_currency", "id_col", "decimal_sep", "drop_empty_amount",
]


class DuplicateFormat(Exception):
    pass


def _clean(value):
    if isinstance(value, str):
        return value.strip() or None
    return value


def normalize_config(raw: dict) -> dict:
    """Bring a config (e.g. from bank_configs.py) into the stored shape."""
    desc_cols = raw.get("desc_cols") or []
    if isinstance(desc_cols, str):
        desc_cols = [desc_cols]
    config = {key: _clean(raw.get(key)) for key in CONFIG_KEYS}
    config.update({
        "bank": (raw.get("bank") or "").strip().lower(),
        "header": [h.strip() for h in raw.get("header", []) if h and h.strip()],
        "desc_cols": [c.strip() for c in desc_cols if c and c.strip()],
        "invert_amount": bool(raw.get("invert_amount", False)),
        "drop_empty_amount": bool(raw.get("drop_empty_amount", True)),
        "sep": raw.get("sep") or ";",          # not stripped: may be a tab
        "encoding": _clean(raw.get("encoding")) or "latin1",
        "decimal_sep": _clean(raw.get("decimal_sep")) or ".",
    })
    if config["fixed_currency"]:
        config["fixed_currency"] = config["fixed_currency"].upper()
    return config


def _row(r) -> dict:
    return {"id": r["id"], "bank": r["bank"], "file_type": r["file_type"],
            "is_active": r["is_active"], "config": r["config"]}


def list_formats(user_id: int, active_only: bool = False) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, bank, file_type, is_active, config FROM bank_formats
                WHERE user_id = :user_id {"AND is_active" if active_only else ""}
                ORDER BY bank, file_type, id
            """),
            {"user_id": user_id}
        ).mappings().all()
    return [_row(r) for r in rows]


def detection_configs(user_id: int) -> list[dict]:
    """Active formats, in the order detection tries them."""
    return [f["config"] for f in list_formats(user_id, active_only=True)]


def available_banks(user_id: int) -> list[str]:
    return sorted({f["bank"] for f in list_formats(user_id)})


def create_format(user_id: int, config: dict, is_active: bool = True) -> int:
    config = normalize_config(config)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO bank_formats (user_id, bank, file_type, config, is_active)
                    VALUES (:user_id, :bank, :file_type, CAST(:config AS JSONB), :is_active)
                    RETURNING id
                """),
                {"user_id": user_id, "bank": config["bank"], "file_type": config["file_type"],
                 "config": json.dumps(config), "is_active": is_active}
            )
            conn.commit()
            return result.scalar()
    except IntegrityError:
        raise DuplicateFormat(f"{config['bank'].upper()} already has a format called '{config['file_type']}'")


def update_format(user_id: int, format_id: int, config: dict, is_active: bool) -> bool:
    config = normalize_config(config)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    UPDATE bank_formats
                    SET bank = :bank, file_type = :file_type, config = CAST(:config AS JSONB),
                        is_active = :is_active, updated_at = NOW()
                    WHERE id = :id AND user_id = :user_id
                """),
                {"id": format_id, "user_id": user_id, "bank": config["bank"], "file_type": config["file_type"],
                 "config": json.dumps(config), "is_active": is_active}
            )
            conn.commit()
            return result.rowcount > 0
    except IntegrityError:
        raise DuplicateFormat(f"{config['bank'].upper()} already has a format called '{config['file_type']}'")


def delete_format(user_id: int, format_id: int) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text("DELETE FROM bank_formats WHERE id = :id AND user_id = :user_id"),
            {"id": format_id, "user_id": user_id}
        )
        conn.commit()
        return result.rowcount > 0


def seed_default_formats(conn, user_id: int) -> None:
    """Give a user the built-in formats from parsers/bank_configs.py (existing ones are kept)."""
    for raw in default_formats():
        config = normalize_config(raw)
        conn.execute(
            text("""
                INSERT INTO bank_formats (user_id, bank, file_type, config)
                VALUES (:user_id, :bank, :file_type, CAST(:config AS JSONB))
                ON CONFLICT (user_id, bank, file_type) DO NOTHING
            """),
            {"user_id": user_id, "bank": config["bank"], "file_type": config["file_type"],
             "config": json.dumps(config)}
        )
