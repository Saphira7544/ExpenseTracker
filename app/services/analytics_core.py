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

A line's `date` is the day it counts on: its real date (`paid_on`), moved to
another month if the transaction or split part has `counts_in` ('YYYY-MM').
Currency conversion always uses `paid_on`, the day the money really moved.

Spending lines in an *occasional* category (default: Travel) also get
`occasional` = True: sporadic spending that isn't part of a normal month. It
still counts in expenses everywhere; totals() reports it separately too, so
the dashboard can show regular spending and what trips take on top.

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


def _month(value) -> str | None:
    return value if isinstance(value, str) and value else None


def counted_date(real: pd.Timestamp, month: str | None) -> pd.Timestamp:
    """`real` moved to `month`, keeping the day where that month has it (31 Jan -> 28 Feb)."""
    if not month:
        return real
    period = pd.Period(month, freq="M")
    return pd.Timestamp(period.year, period.month, min(real.day, period.days_in_month))


def build_lines(transactions: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    """Replace each split transaction by its split rows.

    A part's amount is relative to the original: positive goes the same way
    as the transaction, negative the other way (e.g. on a repayment from a
    friend, "-40 Travel" is your share of a trip they paid). A transaction
    marked Split with no split rows (shouldn't happen) is kept as-is.
    Lines get a `note`: the split part's note, if any. A part with no `counts_in`
    of its own follows the transaction's.
    """
    if "counts_in" not in transactions:
        transactions = transactions.assign(counts_in=None)
    if "counts_in" not in splits:
        splits = splits.assign(counts_in=None)
    is_split = transactions["category"] == SPLIT
    has_rows = transactions["transaction_id"].isin(splits["transaction_id"])
    expand = is_split & has_rows

    plain = transactions.loc[~expand, LINE_COLUMNS + ["counts_in"]].assign(note=None)
    parents = transactions.loc[expand, ["transaction_id", "date", "description", "currency", "amount", "counts_in"]]
    parents = parents.rename(columns={"amount": "parent_amount", "counts_in": "parent_counts_in"})
    parts = splits.merge(parents, on="transaction_id", how="inner")
    parts["amount"] = np.sign(parts["parent_amount"].astype(float)) * parts["amount"].astype(float)
    if "note" not in parts:
        parts["note"] = None

    parts["counts_in"] = [_month(own) or _month(parent) for own, parent in zip(parts["counts_in"], parts["parent_counts_in"])]

    lines = pd.concat([plain, parts[LINE_COLUMNS + ["note", "counts_in"]]], ignore_index=True)
    lines["category"] = lines["category"].fillna(UNCATEGORIZED)
    lines["paid_on"] = pd.to_datetime(lines["date"])
    lines["date"] = pd.to_datetime([counted_date(d, _month(m)) for d, m in zip(lines["paid_on"], lines["counts_in"])])
    lines["amount"] = lines["amount"].astype(float)
    return lines


def classify(lines: pd.DataFrame, income_categories, investment_categories, ignored_categories=(),
             occasional_categories=()) -> pd.DataFrame:
    lines = lines.copy()
    category = lines["category"]
    lines["kind"] = np.select(
        [category.isin(list(ignored_categories)),
         category.isin(list(income_categories)),
         category.isin(list(investment_categories))],
        [IGNORED, INCOME, INVESTMENT],
        default=SPENDING,
    )
    lines["occasional"] = (lines["kind"] == SPENDING) & category.isin(list(occasional_categories))
    return lines


def _r(x: float) -> float:
    return round(float(x), 2) + 0.0  # + 0.0 turns -0.0 into 0.0


def _sum(lines: pd.DataFrame, kind: str) -> float:
    return float(lines.loc[lines["kind"] == kind, "value"].sum())


def _rate(saved: float, income: float) -> float:
    return round(saved / income * 100, 1) if income > 0 else 0


def totals(lines: pd.DataFrame) -> dict:
    income = _sum(lines, INCOME)
    expenses = _sum(lines, SPENDING)        # net spending, normally negative
    invested = -_sum(lines, INVESTMENT)     # money put into investments
    net = income + expenses                 # investments count as saved
    # Occasional spending (trips) apart: what a normal month leaves, before it.
    occasional = float(lines.loc[(lines["kind"] == SPENDING) & lines["occasional"], "value"].sum())         if "occasional" in lines else 0.0
    regular = expenses - occasional
    return {
        "income": _r(income),
        "expenses": _r(expenses),
        "invested": _r(invested),
        "net": _r(net),
        "savings_rate": _rate(net, income),
        "regular_expenses": _r(regular),
        "occasional": _r(occasional),       # negative, like expenses
        "net_regular": _r(income + regular),
        "savings_rate_regular": _rate(income + regular, income),
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
        {k: r[k] for k in ("period", "savings_rate", "net", "income", "savings_rate_regular", "net_regular")}
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
            "paid_on": r.paid_on.date().isoformat(),
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


def monthly_average(lines: pd.DataFrame, current_month: str) -> dict | None:
    """totals() per month on average, over complete months only.

    `current_month` ('YYYY-MM', normally today's) is still in progress, so it
    and anything after it are left out: its expenses aren't all in yet. The
    window runs from the first to the last remaining month with any data,
    counting the months in between even if they're empty (a month with no
    spending is real). None when no complete month is left.
    """
    if lines.empty:
        return None
    period = periods(lines, "%Y-%m")
    done = lines[period < current_month]
    if done.empty:
        return None
    done_period = period[period < current_month]
    first, last = done_period.min(), done_period.max()
    months = len(pd.period_range(first, last, freq="M"))
    t = totals(done)
    return {
        "months": months,
        "from": first,
        "to": last,
        "left_out": sorted(set(period[period >= current_month])),
        **{k: _r(t[k] / months) for k in
           ("income", "expenses", "invested", "net", "regular_expenses", "occasional", "net_regular")},
        # Ratios: the same over the whole window.
        "savings_rate": t["savings_rate"],
        "savings_rate_regular": t["savings_rate_regular"],
    }


def occasional_lines(lines: pd.DataFrame, limit: int = 12) -> list[dict]:
    """The biggest occasional spending lines (trips), largest first."""
    occasional = lines[(lines["kind"] == SPENDING) & lines["occasional"]]
    biggest = occasional.sort_values("value", kind="stable").head(limit)   # most negative first
    return [
        {
            "transaction_id": r.transaction_id,
            "date": r.date.date().isoformat(),
            "paid_on": r.paid_on.date().isoformat(),
            "description": r.description,
            "category": r.category,
            "spent": _r(-r.value),
        }
        for r in biggest.itertuples(index=False)
        if r.value < 0
    ]


# With fewer complete months the projection was far off when tested on past years
# (one salary landing in the wrong month moves it a lot).
MIN_MONTHS_FOR_PROJECTION = 6


def year_end_projection(lines: pd.DataFrame, current_month: str) -> dict | None:
    """Where this year's savings rate is heading: an estimate, not a forecast.

    Known: the year's complete months, as they happened. For the months left:
    - income as those months paid last year, because salaries don't arrive
      evenly (e.g. January's can land in December). A month from before any
      income was recorded uses this year's average instead.
    - spending at this year's monthly average so far (trips included).

    `lines` must include last year. None too early in the year to be meaningful.
    """
    year = int(current_month[:4])
    per_month = {r["period"]: r for r in trend(lines, "%Y-%m")}
    done = [p for p in per_month if p.startswith(f"{year}-") and p < current_month]
    if not done:
        return None
    last_done = int(max(done)[5:])
    if last_done < MIN_MONTHS_FOR_PROJECTION:
        return None

    def so_far(key: str) -> float:
        return sum(per_month.get(f"{year}-{m:02d}", {}).get(key, 0.0) for m in range(1, last_done + 1))

    income_months = [p for p, r in per_month.items() if r["income"] > 0]
    first_income = min(income_months) if income_months else None
    months_left = list(range(last_done + 1, 13))

    income = so_far("income")
    average_income = income / last_done
    from_last_year = 0
    for m in months_left:
        same_month = f"{year - 1}-{m:02d}"
        if first_income and same_month >= first_income:
            income += per_month.get(same_month, {}).get("income", 0.0)
            from_last_year += 1
        else:
            income += average_income
    if income <= 0:
        return None

    average_expenses = so_far("expenses") / last_done
    expenses = so_far("expenses") + average_expenses * len(months_left)
    regular = so_far("regular_expenses") * 12 / last_done
    return {
        "year": str(year),
        "months_known": last_done,
        "months_left": len(months_left),
        "income_from_last_year": from_last_year == len(months_left),
        "income": _r(income),
        "expenses": _r(expenses),
        "net": _r(income + expenses),
        "savings_rate": _rate(income + expenses, income),
        "net_regular": _r(income + regular),
        "savings_rate_regular": _rate(income + regular, income),
    }
