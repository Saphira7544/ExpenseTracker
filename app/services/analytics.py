import pandas as pd
from sqlalchemy import text

from app.db.session import engine
from app.services import analytics_core as core
from app.services import fx
from app.services.settings import get_settings, SUPPORTED_DISPLAY_CURRENCIES


# ---------------------------------------------------------------------------
# Shared loading: transactions -> lines (splits expanded) -> converted values
# ---------------------------------------------------------------------------

def _load_frames(user_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    with engine.connect() as conn:
        tx_rows = conn.execute(text("""
            SELECT transactionId AS transaction_id, date, description, category, amount, currency
            FROM transactions
            WHERE user_id = :user_id
        """), {"user_id": user_id}).mappings().all()
        split_rows = conn.execute(text("""
            SELECT transactionId AS transaction_id, category, amount, note
            FROM transaction_splits
            WHERE user_id = :user_id
        """), {"user_id": user_id}).mappings().all()

    tx = pd.DataFrame([dict(r) for r in tx_rows], columns=core.TX_COLUMNS)
    tx["date"] = pd.to_datetime(tx["date"])
    tx["currency"] = tx["currency"].astype(str).str.strip().str.upper()
    splits = pd.DataFrame([dict(r) for r in split_rows], columns=core.SPLIT_COLUMNS + ["note"])
    return tx, splits


def _prepare(user_id: int, currency: str | None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Lines with `value` (in the display currency) and `kind`, the raw
    transactions, and metadata about the conversion for the response."""
    settings = get_settings(user_id)
    target = currency if currency in SUPPORTED_DISPLAY_CURRENCIES else settings["display_currency"]

    tx, splits = _load_frames(user_id)
    lines = core.build_lines(tx, splits)

    missing: list[str] = []
    if lines.empty:
        lines["value"] = pd.Series(dtype=float)
    else:
        currencies = set(lines["currency"]) | {target}
        fx.ensure_rates(currencies, lines["date"].min().date())
        lines["value"], missing = fx.convert(lines, target, fx.load_rates(currencies))
        lines = lines.dropna(subset=["value"])

    lines = core.classify(lines, settings["income_categories"], settings["investment_categories"],
                          settings["ignored_categories"])
    meta = {
        "currency": target,
        "available_currencies": SUPPORTED_DISPLAY_CURRENCIES,
        "converted_currencies": sorted(set(tx["currency"]) - {target}),
        "fx_missing": missing,
        "fx_source": fx.SOURCE_LABEL,
    }
    return lines, tx, meta


# ---------------------------------------------------------------------------
# DASHBOARD (annual / all-time) — used by "/"
# ---------------------------------------------------------------------------

def get_overview_bundle(user_id: int, year: str | None = None, currency: str | None = None) -> dict:
    """
    - year == None or 'all'  -> one point PER YEAR
    - year == 'YYYY'         -> one point PER MONTH within that year
    """
    lines, tx, meta = _prepare(user_id, currency)
    available_years = sorted(set(tx["date"].dt.strftime("%Y")), reverse=True)
    selected_year = year or "all"

    if selected_year == "all":
        scoped, fmt = lines, "%Y"
    else:
        scoped, fmt = lines[core.periods(lines, "%Y") == selected_year], "%Y-%m"

    trend = core.trend(scoped, fmt)
    return {
        "available_years": available_years,
        "selected_year": selected_year,
        "summary": core.totals(scoped),
        "income_expenses_trend": trend,
        "savings_rate_trend": core.savings_rate_trend(trend),
        "category_heatmap": core.category_heatmap(scoped),
        **meta,
    }


# ---------------------------------------------------------------------------
# MONTHLY — used by "/monthly"
# ---------------------------------------------------------------------------

def get_monthly_bundle(user_id: int, month: str | None = None, currency: str | None = None) -> dict:
    lines, tx, meta = _prepare(user_id, currency)
    tx_months = tx["date"].dt.strftime("%Y-%m")
    available_months = sorted(set(tx_months), reverse=True)
    selected_month = month or (available_months[0] if available_months else None)

    if not selected_month:
        return {
            "available_months": [], "selected_month": None, "month_summary": None,
            "lines": [], "history": None, **meta,
        }

    scoped = lines[core.periods(lines, "%Y-%m") == selected_month]
    return {
        "available_months": available_months,
        "selected_month": selected_month,
        "month_summary": core.month_summary(scoped, txn_count=int((tx_months == selected_month).sum())),
        # Every spending line of the month: the page filters and aggregates them
        # itself, so clicking a category or a day updates every chart instantly.
        "lines": core.spending_lines(scoped),
        "history": core.category_history(lines, selected_month),
        **meta,
    }


# ---------------------------------------------------------------------------
# NET WORTH — used by "/networth/analytics" (unchanged from before)
# ---------------------------------------------------------------------------

def get_networth_trend(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                snapshot_date,
                total_liquid_chf,
                total_illiquid_chf,
                total_networth_chf,
                mom_change_pct
            FROM networth_snapshots
            WHERE user_id = :user_id
            ORDER BY snapshot_date ASC
        """), {"user_id": user_id}).mappings().all()
    return [dict(r) for r in rows]


def get_investment_trend(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                v.valuation_date,
                ac.name AS asset_category,
                a.account_name,
                SUM(v.current_value_chf) AS total_chf
            FROM networth_valuations v
            JOIN networth_accounts a ON v.account_id = a.id
            LEFT JOIN networth_asset_categories ac ON a.asset_category_id = ac.id
            WHERE v.user_id = :user_id
              AND (
                LOWER(COALESCE(ac.name, '')) LIKE '%%invest%%'
                OR LOWER(COALESCE(ac.name, '')) LIKE '%%stock%%'
                OR LOWER(COALESCE(ac.name, '')) LIKE '%%etf%%'
                OR LOWER(COALESCE(ac.name, '')) LIKE '%%fund%%'
                OR LOWER(COALESCE(ac.name, '')) LIKE '%%crypto%%'
              )
            GROUP BY v.valuation_date, ac.name, a.account_name
            ORDER BY v.valuation_date ASC
        """), {"user_id": user_id}).mappings().all()

    by_date = {}
    for r in rows:
        d = r["valuation_date"].isoformat() if hasattr(r["valuation_date"], "isoformat") else str(r["valuation_date"])
        by_date[d] = by_date.get(d, 0.0) + float(r["total_chf"] or 0)

    return [{"date": d, "total_chf": v} for d, v in sorted(by_date.items())]


def get_asset_allocation(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                COALESCE(ac.name, 'Unclassified') AS asset_category,
                SUM(v.current_value_chf) AS total_chf
            FROM networth_valuations v
            JOIN networth_accounts a ON v.account_id = a.id
            LEFT JOIN networth_asset_categories ac ON a.asset_category_id = ac.id
            WHERE v.user_id = :user_id
              AND v.valuation_date = (
                  SELECT MAX(v2.valuation_date)
                  FROM networth_valuations v2
                  WHERE v2.account_id = a.id AND v2.user_id = :user_id
              )
            GROUP BY COALESCE(ac.name, 'Unclassified')
            ORDER BY total_chf DESC
        """), {"user_id": user_id}).mappings().all()
    return [dict(r) for r in rows]


def get_liquidity_split(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                COALESCE(ls.name, 'Unclassified') AS liquidity_status,
                SUM(v.current_value_chf) AS total_chf
            FROM networth_valuations v
            JOIN networth_accounts a ON v.account_id = a.id
            LEFT JOIN networth_liquidity_statuses ls ON a.liquidity_status_id = ls.id
            WHERE v.user_id = :user_id
              AND v.valuation_date = (
                  SELECT MAX(v2.valuation_date)
                  FROM networth_valuations v2
                  WHERE v2.account_id = a.id AND v2.user_id = :user_id
              )
            GROUP BY COALESCE(ls.name, 'Unclassified')
            ORDER BY total_chf DESC
        """), {"user_id": user_id}).mappings().all()
    return [dict(r) for r in rows]


def get_institution_allocation(user_id: int) -> list[dict]:
    """Latest value per account, summed by institution."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                COALESCE(i.name, 'No institution') AS institution,
                SUM(v.current_value_chf) AS total_chf
            FROM networth_valuations v
            JOIN networth_accounts a ON v.account_id = a.id
            LEFT JOIN networth_institutions i ON a.institution_id = i.id
            WHERE v.user_id = :user_id
              AND v.valuation_date = (
                  SELECT MAX(v2.valuation_date)
                  FROM networth_valuations v2
                  WHERE v2.account_id = a.id AND v2.user_id = :user_id
              )
            GROUP BY COALESCE(i.name, 'No institution')
            ORDER BY total_chf DESC
        """), {"user_id": user_id}).mappings().all()
    return [dict(r) for r in rows]


def get_networth_analytics_bundle(user_id: int) -> dict:
    return {
        "institution_allocation": get_institution_allocation(user_id),
        "networth_trend": get_networth_trend(user_id),
        "investment_trend": get_investment_trend(user_id),
        "asset_allocation": get_asset_allocation(user_id),
        "liquidity_split": get_liquidity_split(user_id),
    }