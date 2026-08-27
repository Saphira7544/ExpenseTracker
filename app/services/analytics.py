from sqlalchemy import text
from app.db.session import engine


def get_available_months(user_id: int) -> list[str]:
    """Distinct 'YYYY-MM' months that have transactions, most recent first."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT to_char(date, 'YYYY-MM') AS ym
            FROM transactions
            WHERE user_id = :user_id
            ORDER BY ym DESC
        """), {"user_id": user_id}).all()
    return [r[0] for r in rows]


def get_month_summary(user_id: int, month: str) -> dict:
    """
    month: 'YYYY-MM'. Returns income, expenses, net, and count for that month.
    Excludes internal transfers/investments from "expenses" bucket where possible,
    but still reports them separately.
    """
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
                COALESCE(SUM(amount) FILTER (WHERE amount > 0), 0) AS income,
                COALESCE(SUM(amount) FILTER (WHERE amount < 0), 0) AS expenses,
                COALESCE(SUM(amount), 0) AS net,
                COUNT(*) AS txn_count
            FROM transactions
            WHERE user_id = :user_id
              AND to_char(date, 'YYYY-MM') = :month
        """), {"user_id": user_id, "month": month}).mappings().first()
    return dict(row) if row else {"income": 0, "expenses": 0, "net": 0, "txn_count": 0}


def get_category_breakdown(user_id: int, month: str) -> list[dict]:
    """Expense total per category for a given month (expenses = negative amounts)."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                COALESCE(category, 'Uncategorized') AS category,
                SUM(ABS(amount)) AS total
            FROM transactions
            WHERE user_id = :user_id
              AND to_char(date, 'YYYY-MM') = :month
              AND amount < 0
            GROUP BY COALESCE(category, 'Uncategorized')
            ORDER BY total DESC
        """), {"user_id": user_id, "month": month}).mappings().all()
    return [dict(r) for r in rows]


def get_income_vs_expenses_trend(user_id: int, months_back: int = 12) -> list[dict]:
    """Monthly income vs expenses vs net (savings) for the last N months."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                to_char(date, 'YYYY-MM') AS month,
                COALESCE(SUM(amount) FILTER (WHERE amount > 0), 0) AS income,
                COALESCE(SUM(amount) FILTER (WHERE amount < 0), 0) AS expenses,
                COALESCE(SUM(amount), 0) AS net
            FROM transactions
            WHERE user_id = :user_id
              AND date >= (CURRENT_DATE - (:months_back || ' months')::interval)
            GROUP BY to_char(date, 'YYYY-MM')
            ORDER BY month ASC
        """), {"user_id": user_id, "months_back": months_back}).mappings().all()
    return [dict(r) for r in rows]


def get_savings_rate_trend(user_id: int, months_back: int = 12) -> list[dict]:
    """
    Savings rate = net / income * 100 for each month.
    Skips months with zero income to avoid divide-by-zero.
    """
    trend = get_income_vs_expenses_trend(user_id, months_back)
    result = []
    for row in trend:
        income = float(row["income"] or 0)
        net = float(row["net"] or 0)
        rate = (net / income * 100) if income > 0 else 0
        result.append({
            "month": row["month"],
            "savings_rate": round(rate, 1),
            "net": net,
            "income": income,
        })
    return result


def get_spending_by_category_trend(user_id: int, months_back: int = 6, top_n: int = 6) -> dict:
    """
    Stacked-area friendly structure: totals per category per month,
    limited to the top_n categories by overall spend (rest bucketed as 'Other').
    """
    with engine.connect() as conn:
        top_rows = conn.execute(text("""
            SELECT COALESCE(category, 'Uncategorized') AS category, SUM(ABS(amount)) AS total
            FROM transactions
            WHERE user_id = :user_id
              AND amount < 0
              AND date >= (CURRENT_DATE - (:months_back || ' months')::interval)
            GROUP BY COALESCE(category, 'Uncategorized')
            ORDER BY total DESC
            LIMIT :top_n
        """), {"user_id": user_id, "months_back": months_back, "top_n": top_n}).all()
        top_categories = [r[0] for r in top_rows]

        rows = conn.execute(text("""
            SELECT
                to_char(date, 'YYYY-MM') AS month,
                COALESCE(category, 'Uncategorized') AS category,
                SUM(ABS(amount)) AS total
            FROM transactions
            WHERE user_id = :user_id
              AND amount < 0
              AND date >= (CURRENT_DATE - (:months_back || ' months')::interval)
            GROUP BY to_char(date, 'YYYY-MM'), COALESCE(category, 'Uncategorized')
            ORDER BY month ASC
        """), {"user_id": user_id, "months_back": months_back}).mappings().all()

    months = sorted({r["month"] for r in rows})
    series = {cat: {m: 0.0 for m in months} for cat in top_categories}
    series["Other"] = {m: 0.0 for m in months}

    for r in rows:
        m, cat, total = r["month"], r["category"], float(r["total"] or 0)
        if cat in series and cat != "Other":
            series[cat][m] += total
        else:
            series["Other"][m] += total

    return {"months": months, "series": series}


def get_networth_trend(user_id: int) -> list[dict]:
    """Historical net worth snapshots (liquid / illiquid / total) over time."""
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
    """
    Value over time of accounts classified as investment-like asset categories
    (anything whose asset_category name contains 'invest' or 'stock' or 'etf' or 'fund' or 'crypto'),
    based on valuation history.
    """
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
    """Current allocation of net worth across asset categories (latest valuation per account)."""
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
    """Current split between liquid and illiquid assets (latest valuation per account)."""
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


def get_top_merchants(user_id: int, month: str, limit: int = 8) -> list[dict]:
    """Biggest spending descriptions for a given month (helps spot recurring big expenses)."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT description, SUM(ABS(amount)) AS total, COUNT(*) AS occurrences
            FROM transactions
            WHERE user_id = :user_id
              AND to_char(date, 'YYYY-MM') = :month
              AND amount < 0
            GROUP BY description
            ORDER BY total DESC
            LIMIT :limit
        """), {"user_id": user_id, "month": month, "limit": limit}).mappings().all()
    return [dict(r) for r in rows]


def get_dashboard_bundle(user_id: int, month: str | None = None) -> dict:
    """Single call that returns everything the /analytics page needs."""
    available_months = get_available_months(user_id)
    selected_month = month or (available_months[0] if available_months else None)

    return {
        "available_months": available_months,
        "selected_month": selected_month,
        "month_summary": get_month_summary(user_id, selected_month) if selected_month else None,
        "category_breakdown": get_category_breakdown(user_id, selected_month) if selected_month else [],
        "top_merchants": get_top_merchants(user_id, selected_month) if selected_month else [],
        "income_expenses_trend": get_income_vs_expenses_trend(user_id, 12),
        "savings_rate_trend": get_savings_rate_trend(user_id, 12),
        "spending_by_category_trend": get_spending_by_category_trend(user_id, 6, 6),
        "networth_trend": get_networth_trend(user_id),
        "investment_trend": get_investment_trend(user_id),
        "asset_allocation": get_asset_allocation(user_id),
        "liquidity_split": get_liquidity_split(user_id),
    }
