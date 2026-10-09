"""Pure analytics calculations (no database access), so they can be unit tested.

The unit of analysis is a *line*: a normal transaction, or one part of a
split transaction. Each line has a date, description, category, amount and
currency, plus (after conversion) `value` in the display currency and a
`kind`:

- income      -> categories the user marked as income (default: Salary)
- investment  -> categories the user marked as investments (default: Investments)
- ignored     -> categories left out of every total (default: Internal, i.e. moving
                 money between your own accounts or currencies, which is neither
                 earned, spent nor invested)
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
INCOME, INVESTMENT, SPENDING, IGNORED = "income", "investment", "spending", "ignored"

TX_COLUMNS = ["transaction_id", "date", "description", "category", "amount", "currency"]
SPLIT_COLUMNS = ["transaction_id", "category", "amount"]
LINE_COLUMNS = ["transaction_id", "date", "description", "category", "amount", "currency"]


def build_lines(transactions: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    """Replace each split transaction by its split rows.

    A part's amount is relative to the original: positive goes the same way
    as the transaction, negative the other way (e.g. on a repayment from a
    friend, "-40 Travel" is your share of a trip they paid). A transaction
    marked Split with no split rows (shouldn't happen) is kept as-is.
    Lines get a `note`: the split part's note, if any.
    """
    is_split = transactions["category"] == SPLIT
    has_rows = transactions["transaction_id"].isin(splits["transaction_id"])
    expand = is_split & has_rows

    plain = transactions.loc[~expand, LINE_COLUMNS].assign(note=None)
    parents = transactions.loc[expand, ["transaction_id", "date", "description", "currency", "amount"]]
    parents = parents.rename(columns={"amount": "parent_amount"})
    parts = splits.merge(parents, on="transaction_id", how="inner")
    parts["amount"] = np.sign(parts["parent_amount"].astype(float)) * parts["amount"].astype(float)
    if "note" not in parts:
        parts["note"] = None

    lines = pd.concat([plain, parts[LINE_COLUMNS + ["note"]]], ignore_index=True)
    lines["category"] = lines["category"].fillna(UNCATEGORIZED)
    lines["date"] = pd.to_datetime(lines["date"])
    lines["amount"] = lines["amount"].astype(float)
    return lines


def classify(lines: pd.DataFrame, income_categories, investment_categories, ignored_categories=()) -> pd.DataFrame:
    lines = lines.copy()
    category = lines["category"]
    lines["kind"] = np.select(
        [category.isin(list(ignored_categories)),
         category.isin(list(income_categories)),
         category.isin(list(investment_categories))],
        [IGNORED, INCOME, INVESTMENT],
        default=SPENDING,
    )
    return lines


def _r(x: float) -> float:
    return round(float(x), 2) + 0.0  # + 0.0 turns -0.0 into 0.0


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


def category_heatmap(lines: pd.DataFrame) -> dict:
    """Net spend per category per month, for a category x month grid.

    `periods` is every month from the first to the last one with spending (so
    the columns are evenly spaced), `rows` one per spending category, biggest
    total first, with only the non-zero months in `values`. A value (or a
    whole row, e.g. Transfers full of repayments) is negative when more came
    back than was spent. `total` is the net spend per month.
    """
    spending = _spending(lines)
    if spending.empty:
        return {"periods": [], "rows": [], "total": {}}
    period = periods(spending, "%Y-%m")
    all_periods = [str(p) for p in pd.period_range(period.min(), period.max(), freq="M")]

    rows = []
    per = -spending.groupby([spending["category"], period])["value"].sum()
    for category, by_period in per.groupby(level=0):
        total = float(by_period.sum())
        rows.append({
            "category": category,
            "total": _r(total),
            "average": _r(total / len(all_periods)),
            "values": {p: _r(v) for (_, p), v in by_period.items() if abs(v) >= 0.005},
        })
    rows.sort(key=lambda r: -r["total"])
    total = -spending.groupby(period)["value"].sum()
    return {"periods": all_periods, "rows": rows, "total": {p: _r(v) for p, v in total.items()}}


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


def spending_lines(lines: pd.DataFrame) -> list[dict]:
    """Every spending line, oldest first. `spent` is positive for money out and
    negative for money back (a refund, or someone paying you back)."""
    spending = _spending(lines).sort_values(["date", "transaction_id"], kind="stable")
    return [
        {
            "transaction_id": r.transaction_id,
            "date": r.date.date().isoformat(),
            "description": r.description,
            "category": r.category,
            "spent": _r(-r.value),
            "amount": _r(r.amount),
            "currency": r.currency,
            "note": r.note if isinstance(r.note, str) and r.note else None,
        }
        for r in spending.itertuples(index=False)
    ]


def category_history(lines: pd.DataFrame, month: str, months: int = 13) -> dict:
    """Net spend per category for `month` and the months before it (months
    without spending are simply absent from a category's values)."""
    end = pd.Period(month, freq="M")
    window = [str(end - i) for i in range(months - 1, -1, -1)]
    spending = _spending(lines)
    period = periods(spending, "%Y-%m")
    spending, period = spending[period.isin(window)], period[period.isin(window)]

    per = -spending.groupby([spending["category"], period])["value"].sum()
    by_category: dict[str, dict] = {}
    for (category, p), v in per.items():
        by_category.setdefault(category, {})[p] = _r(v)
    total = -spending.groupby(period)["value"].sum()
    return {"months": window, "by_category": by_category, "total": {p: _r(v) for p, v in total.items()}}
