from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.db.session import engine


class LookupInUse(Exception):
    pass


class LookupDuplicate(Exception):
    pass


class SnapshotDateTaken(Exception):
    pass


SNAPSHOT_DATE_TAKEN = "There is already a snapshot on this date; edit that one instead."

LOOKUP_TABLES = {
    "institutions": ("networth_institutions", "name"),
    "asset_categories": ("networth_asset_categories", "name"),
    "account_types": ("networth_account_types", "name"),
    "currencies": ("networth_currencies", "code"),
    "liquidity_statuses": ("networth_liquidity_statuses", "name"),
}

ACCOUNT_LOOKUP_FIELDS = {
    "institution_id": "networth_institutions",
    "asset_category_id": "networth_asset_categories",
    "account_type_id": "networth_account_types",
    "currency_id": "networth_currencies",
    "liquidity_status_id": "networth_liquidity_statuses",
}

def _owned_by(conn, table: str, row_id: int, user_id: int) -> bool:
    return conn.execute(
        text(f"SELECT 1 FROM {table} WHERE id = :id AND user_id = :user_id"),
        {"id": row_id, "user_id": user_id},
    ).first() is not None

def account_refs_belong_to_user(user_id: int, payload: dict) -> bool:
    """IDs are plain integers from the client; make sure they are this user's rows."""
    with engine.connect() as conn:
        return all(
            payload.get(field) is None or _owned_by(conn, table, payload[field], user_id)
            for field, table in ACCOUNT_LOOKUP_FIELDS.items()
        )

def account_belongs_to_user(user_id: int, account_id: int) -> bool:
    with engine.connect() as conn:
        return _owned_by(conn, "networth_accounts", account_id, user_id)

def list_lookup(table_key: str, user_id: int) -> list[dict]:
    table, value_col = LOOKUP_TABLES[table_key]
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, {value_col} AS value, sort_order, is_active
            FROM {table}
            WHERE user_id = :user_id
            ORDER BY sort_order, {value_col}
        """), {"user_id": user_id}).mappings().all()
    return [dict(r) for r in rows]

def create_lookup(table_key: str, user_id: int, value: str, sort_order: int = 0) -> int:
    try:
        return _create_lookup(table_key, user_id, value, sort_order)
    except IntegrityError:
        raise LookupDuplicate(f'"{value.strip()}" is already in the list.')


def _create_lookup(table_key: str, user_id: int, value: str, sort_order: int = 0) -> int:
    table, value_col = LOOKUP_TABLES[table_key]
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            INSERT INTO {table} (user_id, {value_col}, sort_order)
            VALUES (:user_id, :value, :sort_order)
            RETURNING id
        """), {
            "user_id": user_id,
            "value": value.strip(),
            "sort_order": sort_order,
        })
        conn.commit()
        return result.scalar()

def update_lookup(table_key: str, user_id: int, item_id: int, value: str, sort_order: int, is_active: bool) -> bool:
    try:
        return _update_lookup(table_key, user_id, item_id, value, sort_order, is_active)
    except IntegrityError:
        raise LookupDuplicate(f'"{value.strip()}" is already in the list.')


def _update_lookup(table_key: str, user_id: int, item_id: int, value: str, sort_order: int, is_active: bool) -> bool:
    table, value_col = LOOKUP_TABLES[table_key]
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            UPDATE {table}
            SET {value_col} = :value, sort_order = :sort_order, is_active = :is_active
            WHERE id = :id AND user_id = :user_id
        """), {
            "id": item_id,
            "user_id": user_id,
            "value": value.strip(),
            "sort_order": sort_order,
            "is_active": is_active,
        })
        conn.commit()
        return result.rowcount > 0

def delete_lookup(table_key: str, user_id: int, item_id: int) -> bool:
    table, _ = LOOKUP_TABLES[table_key]
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                DELETE FROM {table}
                WHERE id = :id AND user_id = :user_id
            """), {"id": item_id, "user_id": user_id})
            conn.commit()
            return result.rowcount > 0
    except IntegrityError:
        # Accounts still reference it (foreign key).
        raise LookupInUse("This value is used by accounts; deactivate it instead, or change those accounts first.")

def get_lookup_bundle(user_id: int) -> dict:
    return {key: list_lookup(key, user_id) for key in LOOKUP_TABLES.keys()}

def list_accounts(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                a.id,
                a.account_name,
                a.ticker_symbol,
                a.is_active,
                a.institution_id,
                i.name AS institution,
                a.asset_category_id,
                ac.name AS asset_category,
                a.account_type_id,
                at.name AS account_type,
                a.currency_id,
                c.code AS currency,
                a.liquidity_status_id,
                ls.name AS liquidity_status
            FROM networth_accounts a
            LEFT JOIN networth_institutions i ON a.institution_id = i.id
            LEFT JOIN networth_asset_categories ac ON a.asset_category_id = ac.id
            LEFT JOIN networth_account_types at ON a.account_type_id = at.id
            LEFT JOIN networth_currencies c ON a.currency_id = c.id
            LEFT JOIN networth_liquidity_statuses ls ON a.liquidity_status_id = ls.id
            WHERE a.user_id = :user_id
            ORDER BY i.name NULLS LAST, a.account_name
        """), {"user_id": user_id}).mappings().all()
    return [dict(r) for r in rows]

def create_account(user_id: int, payload: dict) -> int:
    with engine.connect() as conn:
        result = conn.execute(text("""
            INSERT INTO networth_accounts (
                user_id, account_name, institution_id, asset_category_id,
                account_type_id, currency_id, liquidity_status_id,
                ticker_symbol, is_active
            )
            VALUES (
                :user_id, :account_name, :institution_id, :asset_category_id,
                :account_type_id, :currency_id, :liquidity_status_id,
                :ticker_symbol, :is_active
            )
            RETURNING id
        """), {
            "user_id": user_id,
            "account_name": payload["account_name"].strip(),
            "institution_id": payload.get("institution_id"),
            "asset_category_id": payload.get("asset_category_id"),
            "account_type_id": payload.get("account_type_id"),
            "currency_id": payload.get("currency_id"),
            "liquidity_status_id": payload.get("liquidity_status_id"),
            "ticker_symbol": (payload.get("ticker_symbol") or "").strip() or None,
            "is_active": payload.get("is_active", True),
        })
        conn.commit()
        return result.scalar()

def update_account(user_id: int, account_id: int, payload: dict) -> bool:
    with engine.connect() as conn:
        result = conn.execute(text("""
            UPDATE networth_accounts
            SET
                account_name = :account_name,
                institution_id = :institution_id,
                asset_category_id = :asset_category_id,
                account_type_id = :account_type_id,
                currency_id = :currency_id,
                liquidity_status_id = :liquidity_status_id,
                ticker_symbol = :ticker_symbol,
                is_active = :is_active
            WHERE id = :id AND user_id = :user_id
        """), {
            "id": account_id,
            "user_id": user_id,
            "account_name": payload["account_name"].strip(),
            "institution_id": payload.get("institution_id"),
            "asset_category_id": payload.get("asset_category_id"),
            "account_type_id": payload.get("account_type_id"),
            "currency_id": payload.get("currency_id"),
            "liquidity_status_id": payload.get("liquidity_status_id"),
            "ticker_symbol": (payload.get("ticker_symbol") or "").strip() or None,
            "is_active": payload.get("is_active", True),
        })
        conn.commit()
        return result.rowcount > 0

def delete_account(user_id: int, account_id: int) -> bool:
    with engine.connect() as conn:
        result = conn.execute(text("""
            DELETE FROM networth_accounts
            WHERE id = :id AND user_id = :user_id
        """), {"id": account_id, "user_id": user_id})
        conn.commit()
        return result.rowcount > 0

def list_valuations(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                v.id,
                v.account_id,
                a.account_name,
                c.code AS currency,
                ls.name AS liquidity_status,
                v.valuation_date,
                v.quantity,
                v.avg_purchase_price,
                v.current_price,
                v.current_value_original,
                v.exchange_rate_to_chf,
                v.current_value_chf,
                v.realized_pnl,
                v.source,
                v.note
            FROM networth_valuations v
            JOIN networth_accounts a ON v.account_id = a.id
            LEFT JOIN networth_currencies c ON a.currency_id = c.id
            LEFT JOIN networth_liquidity_statuses ls ON a.liquidity_status_id = ls.id
            WHERE v.user_id = :user_id
            ORDER BY v.valuation_date DESC, a.account_name
        """), {"user_id": user_id}).mappings().all()
    return [dict(r) for r in rows]

def create_valuation(user_id: int, payload: dict) -> int:
    with engine.connect() as conn:
        result = conn.execute(text("""
            INSERT INTO networth_valuations (
                user_id, account_id, valuation_date, quantity, avg_purchase_price,
                current_price, current_value_original, exchange_rate_to_chf,
                current_value_chf, realized_pnl, source, note
            )
            VALUES (
                :user_id, :account_id, :valuation_date, :quantity, :avg_purchase_price,
                :current_price, :current_value_original, :exchange_rate_to_chf,
                :current_value_chf, :realized_pnl, :source, :note
            )
            RETURNING id
        """), {
            "user_id": user_id,
            "account_id": payload["account_id"],
            "valuation_date": payload["valuation_date"],
            "quantity": payload.get("quantity"),
            "avg_purchase_price": payload.get("avg_purchase_price"),
            "current_price": payload.get("current_price"),
            "current_value_original": payload.get("current_value_original"),
            "exchange_rate_to_chf": payload.get("exchange_rate_to_chf"),
            "current_value_chf": payload["current_value_chf"],
            "realized_pnl": payload.get("realized_pnl", 0),
            "source": (payload.get("source") or "manual").strip(),
            "note": (payload.get("note") or "").strip() or None,
        })
        conn.commit()
        return result.scalar()

def update_valuation(user_id: int, valuation_id: int, payload: dict) -> bool:
    with engine.connect() as conn:
        result = conn.execute(text("""
            UPDATE networth_valuations
            SET
                account_id = :account_id,
                valuation_date = :valuation_date,
                quantity = :quantity,
                avg_purchase_price = :avg_purchase_price,
                current_price = :current_price,
                current_value_original = :current_value_original,
                exchange_rate_to_chf = :exchange_rate_to_chf,
                current_value_chf = :current_value_chf,
                realized_pnl = :realized_pnl,
                source = :source,
                note = :note
            WHERE id = :id AND user_id = :user_id
        """), {
            "id": valuation_id,
            "user_id": user_id,
            "account_id": payload["account_id"],
            "valuation_date": payload["valuation_date"],
            "quantity": payload.get("quantity"),
            "avg_purchase_price": payload.get("avg_purchase_price"),
            "current_price": payload.get("current_price"),
            "current_value_original": payload.get("current_value_original"),
            "exchange_rate_to_chf": payload.get("exchange_rate_to_chf"),
            "current_value_chf": payload["current_value_chf"],
            "realized_pnl": payload.get("realized_pnl", 0),
            "source": (payload.get("source") or "manual").strip(),
            "note": (payload.get("note") or "").strip() or None,
        })
        conn.commit()
        return result.rowcount > 0

def delete_valuation(user_id: int, valuation_id: int) -> bool:
    with engine.connect() as conn:
        result = conn.execute(text("""
            DELETE FROM networth_valuations
            WHERE id = :id AND user_id = :user_id
        """), {"id": valuation_id, "user_id": user_id})
        conn.commit()
        return result.rowcount > 0

def list_snapshots(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT *
            FROM networth_snapshots
            WHERE user_id = :user_id
            ORDER BY snapshot_date DESC
        """), {"user_id": user_id}).mappings().all()
    return [dict(r) for r in rows]

def _recompute_snapshot_changes(conn, user_id: int) -> None:
    """Change vs the previous snapshot, for every snapshot in date order.
    Recomputed after any create/edit/delete so the chain never goes stale."""
    rows = conn.execute(text("""
        SELECT id, total_networth_chf FROM networth_snapshots
        WHERE user_id = :user_id ORDER BY snapshot_date
    """), {"user_id": user_id}).all()
    previous = None
    for snapshot_id, total in rows:
        change = pct = None
        if previous not in (None, 0):
            change = float(total) - float(previous)
            pct = change / float(previous) * 100
        conn.execute(text("""
            UPDATE networth_snapshots SET mom_change_chf = :change, mom_change_pct = :pct
            WHERE id = :id
        """), {"change": change, "pct": pct, "id": snapshot_id})
        previous = total


def create_snapshot(user_id: int, payload: dict) -> int:
    try:
        return _create_snapshot(user_id, payload)
    except IntegrityError:
        raise SnapshotDateTaken(SNAPSHOT_DATE_TAKEN)


def _create_snapshot(user_id: int, payload: dict) -> int:
    mom_change_chf = mom_change_pct = None   # filled in by _recompute_snapshot_changes

    with engine.connect() as conn:
        result = conn.execute(text("""
            INSERT INTO networth_snapshots (
                user_id, snapshot_date, total_liquid_chf, total_illiquid_chf,
                total_networth_chf, mom_change_chf, mom_change_pct, notes
            )
            VALUES (
                :user_id, :snapshot_date, :total_liquid_chf, :total_illiquid_chf,
                :total_networth_chf, :mom_change_chf, :mom_change_pct, :notes
            )
            RETURNING id
        """), {
            "user_id": user_id,
            "snapshot_date": payload["snapshot_date"],
            "total_liquid_chf": payload["total_liquid_chf"],
            "total_illiquid_chf": payload["total_illiquid_chf"],
            "total_networth_chf": payload["total_networth_chf"],
            "mom_change_chf": mom_change_chf,
            "mom_change_pct": mom_change_pct,
            "notes": (payload.get("notes") or "").strip() or None,
        })
        snapshot_id = result.scalar()
        _recompute_snapshot_changes(conn, user_id)
        conn.commit()
        return snapshot_id

def update_snapshot(user_id: int, snapshot_id: int, payload: dict) -> bool:
    try:
        return _update_snapshot(user_id, snapshot_id, payload)
    except IntegrityError:
        raise SnapshotDateTaken(SNAPSHOT_DATE_TAKEN)


def _update_snapshot(user_id: int, snapshot_id: int, payload: dict) -> bool:
    with engine.connect() as conn:
        result = conn.execute(text("""
            UPDATE networth_snapshots
            SET
                snapshot_date = :snapshot_date,
                total_liquid_chf = :total_liquid_chf,
                total_illiquid_chf = :total_illiquid_chf,
                total_networth_chf = :total_networth_chf,
                notes = :notes
            WHERE id = :id AND user_id = :user_id
        """), {
            "id": snapshot_id,
            "user_id": user_id,
            "snapshot_date": payload["snapshot_date"],
            "total_liquid_chf": payload["total_liquid_chf"],
            "total_illiquid_chf": payload["total_illiquid_chf"],
            "total_networth_chf": payload["total_networth_chf"],
            "notes": (payload.get("notes") or "").strip() or None,
        })
        _recompute_snapshot_changes(conn, user_id)
        conn.commit()
        return result.rowcount > 0

def delete_snapshot(user_id: int, snapshot_id: int) -> bool:
    with engine.connect() as conn:
        result = conn.execute(text("""
            DELETE FROM networth_snapshots
            WHERE id = :id AND user_id = :user_id
        """), {"id": snapshot_id, "user_id": user_id})
        _recompute_snapshot_changes(conn, user_id)
        conn.commit()
        return result.rowcount > 0

def get_networth_dashboard(user_id: int) -> dict:
    accounts = list_accounts(user_id)
    valuations = list_valuations(user_id)
    snapshots = list_snapshots(user_id)

    latest_snapshot = snapshots[0] if snapshots else None
    return {
        "accounts": accounts,
        "valuations": valuations,
        "snapshots": snapshots,
        "latest_snapshot": latest_snapshot,
        "lookups": get_lookup_bundle(user_id),
    }

def compute_snapshot_from_valuations(user_id: int) -> dict:
    """
    Sums current_value_chf across valuations grouped by liquidity status of accounts.
    Returns: { total_liquid_chf, total_illiquid_chf, total_networth_chf, snapshot_date }
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT a.liquidity_status_id, ls.name AS liquidity_name, SUM(v.current_value_chf) AS total_chf
            FROM networth_valuations v
            JOIN networth_accounts a ON v.account_id = a.id
            LEFT JOIN networth_liquidity_statuses ls ON a.liquidity_status_id = ls.id
            WHERE v.user_id = :user_id
              AND v.valuation_date = (
                  SELECT MAX(v2.valuation_date)
                  FROM networth_valuations v2
                  WHERE v2.account_id = a.id
                    AND v2.user_id = :user_id
              )
            GROUP BY a.liquidity_status_id, ls.name
        """), {"user_id": user_id}).mappings().all()

    totals = {"total_liquid_chf": 0.0, "total_illiquid_chf": 0.0}
    
    for r in rows:
        name = (r["liquidity_name"] or "").lower()
        val = float(r["total_chf"] or 0)
        
        # If the category name contains 'liquid' but not 'illiquid'
        if "liquid" in name and "illiquid" not in name:
            totals["total_liquid_chf"] += val
        else:
            totals["total_illiquid_chf"] += val
            
    totals["total_networth_chf"] = totals["total_liquid_chf"] + totals["total_illiquid_chf"]
    
    from datetime import date
    totals["snapshot_date"] = date.today().isoformat()
    
    return totals
