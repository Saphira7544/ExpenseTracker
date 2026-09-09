from sqlalchemy import text, bindparam
from app.db.session import engine

EXCLUDED_FROM_EXPENSES = ["Investments"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def get_available_months(user_id: int) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT to_char(date, 'YYYY-MM') AS ym
            FROM transactions
            WHERE user_id = :user_id
            ORDER BY ym DESC
        """), {"user_id": user_id}).all()
    return [r[0] for r in rows]


def get_available_years(user_id: int) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT to_char(date, 'YYYY') AS yr
            FROM transactions
            WHERE user_id = :user_id
            ORDER BY yr DESC
        """), {"user_id": user_id}).all()
    return [r[0] for r in rows]

# ---------------------------------------------------------------------------
# DASHBOARD (annual / all-time) — used by "/"
# ---------------------------------------------------------------------------

def get_overview_trend(user_id: int, year: str | None) -> list[dict]:
    """
    Income vs TRUE expenses (excluding Investments) vs invested vs net.
    - year == None or 'all'  -> one point PER YEAR
    - year == 'YYYY'         -> one point PER MONTH within that year
    """
    query_all = text("""
        SELECT
            to_char(date, 'YYYY') AS period,
            COALESCE(SUM(amount) FILTER (WHERE amount > 0), 0) AS income,
            COALESCE(SUM(amount) FILTER (
                WHERE amount < 0 AND COALESCE(category, '') NOT IN :excluded
            ), 0) AS expenses,
            COALESCE(SUM(ABS(amount)) FILTER (
                WHERE amount < 0 AND category IN :excluded
            ), 0) AS invested
        FROM transactions
        WHERE user_id = :user_id
        GROUP BY to_char(date, 'YYYY')
        ORDER BY period ASC
    """).bindparams(bindparam("excluded", expanding=True))

    query_year = text("""
        SELECT
            to_char(date, 'YYYY-MM') AS period,
            COALESCE(SUM(amount) FILTER (WHERE amount > 0), 0) AS income,
            COALESCE(SUM(amount) FILTER (
                WHERE amount < 0 AND COALESCE(category, '') NOT IN :excluded
            ), 0) AS expenses,
            COALESCE(SUM(ABS(amount)) FILTER (
                WHERE amount < 0 AND category IN :excluded
            ), 0) AS invested
        FROM transactions
        WHERE user_id = :user_id
          AND to_char(date, 'YYYY') = :year
        GROUP BY to_char(date, 'YYYY-MM')
        ORDER BY period ASC
    """).bindparams(bindparam("excluded", expanding=True))

    with engine.connect() as conn:
        if not year or year == "all":
            rows = conn.execute(query_all, {
                "user_id": user_id, "excluded": EXCLUDED_FROM_EXPENSES
            }).mappings().all()
        else:
            rows = conn.execute(query_year, {
                "user_id": user_id, "year": year, "excluded": EXCLUDED_FROM_EXPENSES
            }).mappings().all()

    result = []
    for r in rows:
        income = float(r["income"] or 0)
        expenses = float(r["expenses"] or 0)
        invested = float(r["invested"] or 0)
        result.append({
            "period": r["period"],
            "income": income,
            "expenses": expenses,
            "invested": invested,
            "net": income + expenses,  # expenses already negative; investments excluded
        })
    return result

def get_overview_summary(user_id: int, year: str | None) -> dict:
    """
    Aggregate totals for the selected year (or all-time) — the same
    underlying numbers as the trend chart, just summed into one figure
    each, for the Dashboard summary cards.
    """
    trend = get_overview_trend(user_id, year)
    income = sum(r["income"] for r in trend)
    expenses = sum(r["expenses"] for r in trend)
    invested = sum(r["invested"] for r in trend)
    net = income + expenses
    return {
        "income": income,
        "expenses": expenses,
        "invested": invested,
        "net": net,
        "savings_rate": (net / income * 100) if income > 0 else 0,
    }

def get_overview_savings_rate(user_id: int, year: str | None) -> list[dict]:
    trend = get_overview_trend(user_id, year)
    result = []
    for row in trend:
        income = row["income"]
        net = row["net"]
        rate = (net / income * 100) if income > 0 else 0
        result.append({
            "period": row["period"],
            "savings_rate": round(rate, 1),
            "net": net,
            "income": income,
        })
    return result


def get_overview_category_trend(user_id: int, year: str | None, top_n: int = 6) -> dict:
    """
    Spending per category per period. Investments (and anything else in
    EXCLUDED_FROM_EXPENSES) are left out entirely — this chart is about
    actual spending, not money moved into investments.
    """
    top_query_all = text("""
        SELECT COALESCE(category, 'Uncategorized') AS category, SUM(ABS(amount)) AS total
        FROM transactions
        WHERE user_id = :user_id AND amount < 0
          AND COALESCE(category, '') NOT IN :excluded
        GROUP BY COALESCE(category, 'Uncategorized')
        ORDER BY total DESC
        LIMIT :top_n
    """).bindparams(bindparam("excluded", expanding=True))

    trend_query_all = text("""
        SELECT
            to_char(date, 'YYYY') AS period,
            COALESCE(category, 'Uncategorized') AS category,
            SUM(ABS(amount)) AS total
        FROM transactions
        WHERE user_id = :user_id AND amount < 0
          AND COALESCE(category, '') NOT IN :excluded
        GROUP BY to_char(date, 'YYYY'), COALESCE(category, 'Uncategorized')
        ORDER BY period ASC
    """).bindparams(bindparam("excluded", expanding=True))

    top_query_year = text("""
        SELECT COALESCE(category, 'Uncategorized') AS category, SUM(ABS(amount)) AS total
        FROM transactions
        WHERE user_id = :user_id AND amount < 0 AND to_char(date, 'YYYY') = :year
          AND COALESCE(category, '') NOT IN :excluded
        GROUP BY COALESCE(category, 'Uncategorized')
        ORDER BY total DESC
        LIMIT :top_n
    """).bindparams(bindparam("excluded", expanding=True))

    trend_query_year = text("""
        SELECT
            to_char(date, 'YYYY-MM') AS period,
            COALESCE(category, 'Uncategorized') AS category,
            SUM(ABS(amount)) AS total
        FROM transactions
        WHERE user_id = :user_id AND amount < 0 AND to_char(date, 'YYYY') = :year
          AND COALESCE(category, '') NOT IN :excluded
        GROUP BY to_char(date, 'YYYY-MM'), COALESCE(category, 'Uncategorized')
        ORDER BY period ASC
    """).bindparams(bindparam("excluded", expanding=True))

    with engine.connect() as conn:
        if not year or year == "all":
            top_rows = conn.execute(top_query_all, {
                "user_id": user_id, "excluded": EXCLUDED_FROM_EXPENSES, "top_n": top_n
            }).all()
            rows = conn.execute(trend_query_all, {
                "user_id": user_id, "excluded": EXCLUDED_FROM_EXPENSES
            }).mappings().all()
        else:
            top_rows = conn.execute(top_query_year, {
                "user_id": user_id, "year": year, "excluded": EXCLUDED_FROM_EXPENSES, "top_n": top_n
            }).all()
            rows = conn.execute(trend_query_year, {
                "user_id": user_id, "year": year, "excluded": EXCLUDED_FROM_EXPENSES
            }).mappings().all()

    top_categories = [r[0] for r in top_rows]
    periods = sorted({r["period"] for r in rows})
    series = {cat: {p: 0.0 for p in periods} for cat in top_categories}
    series["Other"] = {p: 0.0 for p in periods}

    for r in rows:
        p, cat, total = r["period"], r["category"], float(r["total"] or 0)
        if cat in series and cat != "Other":
            series[cat][p] += total
        else:
            series["Other"][p] += total

    return {"periods": periods, "series": series}


def get_overview_bundle(user_id: int, year: str | None = None) -> dict:
    available_years = get_available_years(user_id)
    selected_year = year or "all"

    return {
        "available_years": available_years,
        "selected_year": selected_year,
        "summary": get_overview_summary(user_id, selected_year),
        "income_expenses_trend": get_overview_trend(user_id, selected_year),
        "savings_rate_trend": get_overview_savings_rate(user_id, selected_year),
        "spending_by_category_trend": get_overview_category_trend(user_id, selected_year, 6),
    }


# ---------------------------------------------------------------------------
# MONTHLY — used by "/monthly"
# ---------------------------------------------------------------------------

def get_month_summary(user_id: int, month: str) -> dict:
    summary_query = text("""
        SELECT
            COALESCE(SUM(amount) FILTER (WHERE amount > 0), 0) AS income,
            COALESCE(SUM(amount) FILTER (
                WHERE amount < 0 AND COALESCE(category, '') NOT IN :excluded
            ), 0) AS expenses,
            COALESCE(SUM(ABS(amount)) FILTER (
                WHERE amount < 0 AND category IN :excluded
            ), 0) AS invested,
            COUNT(*) AS txn_count,
            COUNT(*) FILTER (
                WHERE amount < 0 AND COALESCE(category, '') NOT IN :excluded
            ) AS expense_count
        FROM transactions
        WHERE user_id = :user_id
          AND to_char(date, 'YYYY-MM') = :month
    """).bindparams(bindparam("excluded", expanding=True))

    biggest_query = text("""
        SELECT description, ABS(amount) AS amount
        FROM transactions
        WHERE user_id = :user_id
          AND to_char(date, 'YYYY-MM') = :month
          AND amount < 0
          AND COALESCE(category, '') NOT IN :excluded
        ORDER BY ABS(amount) DESC
        LIMIT 1
    """).bindparams(bindparam("excluded", expanding=True))

    with engine.connect() as conn:
        row = conn.execute(summary_query, {
            "user_id": user_id, "month": month, "excluded": EXCLUDED_FROM_EXPENSES
        }).mappings().first()

        biggest = conn.execute(biggest_query, {
            "user_id": user_id, "month": month, "excluded": EXCLUDED_FROM_EXPENSES
        }).mappings().first()

    summary = dict(row) if row else {
        "income": 0, "expenses": 0, "invested": 0, "net": 0,
        "txn_count": 0, "expense_count": 0
    }

    income = float(summary["income"] or 0)
    expenses = float(summary["expenses"] or 0)
    summary["income"] = income
    summary["expenses"] = expenses
    summary["invested"] = float(summary["invested"] or 0)
    summary["net"] = income + expenses  # investments excluded from this

    expense_count = summary.get("expense_count") or 0
    summary["avg_expense"] = abs(expenses) / expense_count if expense_count > 0 else 0
    summary["savings_rate"] = (summary["net"] / income * 100) if income > 0 else 0
    summary["biggest_expense_description"] = biggest["description"] if biggest else None
    summary["biggest_expense_amount"] = float(biggest["amount"]) if biggest else 0

    return summary


def get_category_breakdown(user_id: int, month: str) -> list[dict]:
    """
    Expenses by category for the pie chart / table. Investments are
    excluded entirely — they get their own "invested" figure instead of
    a slice here.
    """
    query = text("""
        SELECT
            COALESCE(category, 'Uncategorized') AS category,
            SUM(ABS(amount)) AS total
        FROM transactions
        WHERE user_id = :user_id
          AND to_char(date, 'YYYY-MM') = :month
          AND amount < 0
          AND COALESCE(category, '') NOT IN :excluded
        GROUP BY COALESCE(category, 'Uncategorized')
        ORDER BY total DESC
    """).bindparams(bindparam("excluded", expanding=True))

    with engine.connect() as conn:
        rows = conn.execute(query, {
            "user_id": user_id, "month": month, "excluded": EXCLUDED_FROM_EXPENSES
        }).mappings().all()
    return [dict(r) for r in rows]


def get_top_merchants(user_id: int, month: str, limit: int = 8) -> list[dict]:
    query = text("""
        SELECT description, SUM(ABS(amount)) AS total, COUNT(*) AS occurrences
        FROM transactions
        WHERE user_id = :user_id
          AND to_char(date, 'YYYY-MM') = :month
          AND amount < 0
          AND COALESCE(category, '') NOT IN :excluded
        GROUP BY description
        ORDER BY total DESC
        LIMIT :limit
    """).bindparams(bindparam("excluded", expanding=True))

    with engine.connect() as conn:
        rows = conn.execute(query, {
            "user_id": user_id, "month": month, "excluded": EXCLUDED_FROM_EXPENSES, "limit": limit
        }).mappings().all()
    return [dict(r) for r in rows]


def get_daily_spend(user_id: int, month: str) -> list[dict]:
    query = text("""
        SELECT date, SUM(ABS(amount)) AS total
        FROM transactions
        WHERE user_id = :user_id
          AND to_char(date, 'YYYY-MM') = :month
          AND amount < 0
          AND COALESCE(category, '') NOT IN :excluded
        GROUP BY date
        ORDER BY date ASC
    """).bindparams(bindparam("excluded", expanding=True))

    with engine.connect() as conn:
        rows = conn.execute(query, {
            "user_id": user_id, "month": month, "excluded": EXCLUDED_FROM_EXPENSES
        }).mappings().all()
    return [{"date": r["date"].isoformat(), "total": float(r["total"] or 0)} for r in rows]


def get_monthly_bundle(user_id: int, month: str | None = None) -> dict:
    available_months = get_available_months(user_id)
    selected_month = month or (available_months[0] if available_months else None)

    return {
        "available_months": available_months,
        "selected_month": selected_month,
        "month_summary": get_month_summary(user_id, selected_month) if selected_month else None,
        "category_breakdown": get_category_breakdown(user_id, selected_month) if selected_month else [],
        "top_merchants": get_top_merchants(user_id, selected_month) if selected_month else [],
        "daily_spend": get_daily_spend(user_id, selected_month) if selected_month else [],
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


def get_networth_analytics_bundle(user_id: int) -> dict:
    return {
        "networth_trend": get_networth_trend(user_id),
        "investment_trend": get_investment_trend(user_id),
        "asset_allocation": get_asset_allocation(user_id),
        "liquidity_split": get_liquidity_split(user_id),
    }