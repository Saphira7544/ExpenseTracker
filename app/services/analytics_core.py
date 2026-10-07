"""Pure analytics calculations (no database access), so they can be unit tested.

The unit of analysis is a *line*: a normal transaction, or one part of a
split transaction. Each line has a date, description, category, amount and
currency, plus (after conversion) `value` in the display currency and a
`kind`:

- income      -> categories the user marked as income (default: Salary)
- investment  -> categories the user marked as investments (default: Investments)
- spending    -> everything else

Spending is *netted per category*: a positive amount in a spending category
(a refund, or someone paying you back) reduces that category instead of
counting as income. E.g. splitting a 100 grocery bill into 50 Groceries +
50 Transfers, then receiving +50 tagged Transfers, leaves Groceries at 50
and Transfers at 0.
"""
import numpy as np
import pandas as pd

SPLIT = "Split"
UNCATEGORIZED = "Uncategorized"
INCOME, INVESTMENT, SPENDING = "income", "investment", "spending"

TX_COLUMNS = ["transaction_id", "date", "description", "category", "amount", "currency"]
SPLIT_COLUMNS = ["transaction_id", "category", "amount"]
LINE_COLUMNS = ["transaction_id", "date", "description", "category", "amount", "currency"]


def build_lines(transactions: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    """Replace each split transaction by its split rows.

    Split amounts are stored as positive numbers; they take the sign of the
    original transaction. A transaction marked Split with no split rows
    (shouldn't happen) is kept as-is so its amount isn't lost.
    """
    is_split = transactions["category"] == SPLIT
    has_rows = transactions["transaction_id"].isin(splits["transaction_id"])
    expand = is_split & has_rows

    plain = transactions.loc[~expand, LINE_COLUMNS]
    parents = transactions.loc[expand, ["transaction_id", "date", "description", "currency", "amount"]]
    parents = parents.rename(columns={"amount": "parent_amount"})
    parts = splits.merge(parents, on="transaction_id", how="inner")
    parts["amount"] = np.sign(parts["parent_amount"].astype(float)) * parts["amount"].astype(float).abs()

    lines = pd.concat([plain, parts[LINE_COLUMNS]], ignore_index=True)
    lines["category"] = lines["category"].fillna(UNCATEGORIZED)
    lines["date"] = pd.to_datetime(lines["date"])
    lines["amount"] = lines["amount"].astype(float)
    return lines


def classify(lines: pd.DataFrame, income_categories, investment_categories) -> pd.DataFrame:
    lines = lines.copy()
    category = lines["category"]
    lines["kind"] = np.where(
        category.isin(list(income_categories)), INCOME,
        np.where(category.isin(list(investment_categories)), INVESTMENT, SPENDING),
    )
    return lines


def _r(x: float) -> float:
    return round(float(x), 2)


def _sum(lines: pd.DataFrame, kind: str) -> float:
    return float(lines.loc[lines["kind"] == kind, "value"].sum())


def totals(lines: pd.DataFrame) -> dict:
    income = _sum(lines, INCOME)
    expenses = _sum(lines, SPENDING)        # net spending, normally negative
    invested = -_sum(lines, INVESTMENT)     # money put into investments
    net = income + expenses                 # investments count as saved
    return {
        "income": _r(income),
        "expenses": _r(expenses),
        "invested": _r(invested),
        "net": _r(net),
        "savings_rate": round(net / income * 100, 1) if income > 0 else 0,
    }


def periods(lines: pd.DataFrame, fmt: str) -> pd.Series:
    return lines["date"].dt.strftime(fmt)


def trend(lines: pd.DataFrame, fmt: str) -> list[dict]:
    """totals() per period; fmt is '%Y' (per year) or '%Y-%m' (per month)."""
    if lines.empty:
        return []
    by_period = periods(lines, fmt)
    return [{"period": p, **totals(group)} for p, group in lines.groupby(by_period, sort=True)]


def savings_rate_trend(trend_rows: list[dict]) -> list[dict]:
    return [
        {"period": r["period"], "savings_rate": r["savings_rate"], "net": r["net"], "income": r["income"]}
        for r in trend_rows
    ]


def _spending(lines: pd.DataFrame) -> pd.DataFrame:
    return lines[lines["kind"] == SPENDING]


def category_breakdown(lines: pd.DataFrame) -> list[dict]:
    """Net spend per category, largest first. A category can be negative when
    more came back than was spent (e.g. a repayment landing in a later month)."""
    spend = -_spending(lines).groupby("category")["value"].sum()
    spend = spend[spend.abs() >= 0.005].sort_values(ascending=False)
    return [{"category": c, "total": _r(v)} for c, v in spend.items()]


def category_trend(lines: pd.DataFrame, fmt: str, top_n: int = 6) -> dict:
    spending = _spending(lines)
    if spending.empty:
        return {"periods": [], "series": {}}
    period = periods(spending, fmt)
    all_periods = sorted(period.unique())

    totals_by_cat = (-spending.groupby("category")["value"].sum()).sort_values(ascending=False)
    top = [c for c, v in totals_by_cat.head(top_n).items() if v > 0]

    series = {c: {p: 0.0 for p in all_periods} for c in top}
    series["Other"] = {p: 0.0 for p in all_periods}
    per = -spending.groupby([period, spending["category"]])["value"].sum()
    for (p, cat), v in per.items():
        key = cat if cat in series and cat != "Other" else "Other"
        series[key][p] += float(v)

    series = {c: {p: _r(v) for p, v in s.items()} for c, s in series.items()}
    return {"periods": all_periods, "series": series}


def month_summary(lines: pd.DataFrame, txn_count: int) -> dict:
    summary = totals(lines)
    outflows = _spending(lines)
    outflows = outflows[outflows["value"] < 0]
    expense_count = len(outflows)

    biggest = outflows.loc[outflows["value"].idxmin()] if expense_count else None
    summary.update({
        "txn_count": int(txn_count),
        "expense_count": expense_count,
        "avg_expense": _r(-outflows["value"].sum() / expense_count) if expense_count else 0,
        "biggest_expense_description": biggest["description"] if biggest is not None else None,
        "biggest_expense_amount": _r(-biggest["value"]) if biggest is not None else 0,
    })
    return summary


def top_merchants(lines: pd.DataFrame, limit: int = 8) -> list[dict]:
    spending = _spending(lines)
    if spending.empty:
        return []
    grouped = spending.groupby("description")["value"].agg(["sum", "count"])
    grouped["total"] = -grouped["sum"]
    grouped = grouped[grouped["total"] > 0].sort_values("total", ascending=False).head(limit)
    return [
        {"description": d, "total": _r(row["total"]), "occurrences": int(row["count"])}
        for d, row in grouped.iterrows()
    ]


def daily_spend(lines: pd.DataFrame) -> list[dict]:
    spending = _spending(lines)
    daily = -spending.groupby(spending["date"].dt.date)["value"].sum()
    return [{"date": d.isoformat(), "total": _r(v)} for d, v in daily.sort_index().items()]
