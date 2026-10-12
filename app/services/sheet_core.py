"""Pure calculations for the Monthly Sheet page (/sheet), no database access.

The page mirrors the old Excel budget sheet: income, savings, totals, and the
month's spending grouped into a few sections (Housing, Food, ...). It works on
the same classified *lines* as the other dashboards (see analytics_core), with
two converted values per line: `value` in the display currency and
`alt_value` in the other one, so every total can be shown in both, like the
sheet's EUR and CHF columns.

Spending is netted per category exactly like the other dashboards, so the
totals here match the Monthly page.
"""
import pandas as pd

from app.services.analytics_core import INCOME, INVESTMENT, SPENDING, periods

USUAL_MONTHS = 12


def _r(x: float) -> float:
    return round(float(x), 2) + 0.0  # + 0.0 turns -0.0 into 0.0


def group_names(categories: pd.Series, groups: list[dict], fallback: str) -> pd.Series:
    """The group of each category; categories no group lists go to `fallback`."""
    lookup = {category: g["name"] for g in groups for category in g["categories"]}
    return categories.map(lambda c: lookup.get(c, fallback))


def _line(r, sign: int) -> dict:
    """One line for the page. `sign` = -1 for money going out (spending,
    investing) so it reads as a positive amount."""
    return {
        "transaction_id": r.transaction_id,
        "date": r.date.date().isoformat(),
        "description": r.description,
        "category": r.category,
        "value": _r(sign * r.value),
        "alt_value": _r(sign * r.alt_value),
        "amount": _r(sign * r.amount),
        "currency": r.currency,
        "note": r.note if isinstance(r.note, str) and r.note else None,
    }


def _lines(df: pd.DataFrame, sign: int) -> list[dict]:
    """Biggest first, then by date."""
    df = df.assign(_sort=sign * df["value"]).sort_values(["_sort", "date"], ascending=[False, True], kind="stable")
    return [_line(r, sign) for r in df.itertuples(index=False)]


def _by_currency(df: pd.DataFrame, sign: int) -> dict:
    """Total per original currency, e.g. {'CHF': 220.62, 'EUR': 25.71}."""
    per = (sign * df.groupby("currency")["amount"].sum())
    return {c: _r(v) for c, v in per.sort_index().items() if abs(v) >= 0.005}


def _section(df: pd.DataFrame, sign: int) -> dict:
    """Total (both currencies), per original currency, per category, and the lines."""
    per_cat = df.groupby("category")[["value", "alt_value"]].sum() * sign
    per_cat = per_cat[per_cat["value"].abs() >= 0.005].sort_values("value", ascending=False)
    return {
        "total": _r(sign * df["value"].sum()),
        "total_alt": _r(sign * df["alt_value"].sum()),
        "by_currency": _by_currency(df, sign),
        "categories": [
            {"category": c, "total": _r(row.value), "total_alt": _r(row.alt_value)}
            for c, row in per_cat.iterrows()
        ],
        "lines": _lines(df, sign),
    }


def _usual(spending: pd.DataFrame, month: str, groups: pd.Series) -> tuple[dict, int]:
    """Average net spend per group in the (up to) 12 months before `month`.

    Only months from the first month with any data count, so a short history
    isn't averaged with empty months before it. Returns ({group: average},
    number of months averaged); groups missing from the dict spent nothing.
    """
    if spending.empty:
        return {}, 0
    end = pd.Period(month, freq="M")
    period = periods(spending, "%Y-%m")
    first = pd.Period(period.min(), freq="M")
    window = [str(end - i) for i in range(USUAL_MONTHS, 0, -1) if end - i >= first]
    if not window:
        return {}, 0
    inside = period.isin(window)
    per = -spending.loc[inside].groupby(groups[inside])["value"].sum()
    return {g: _r(v / len(window)) for g, v in per.items()}, len(window)


def month_sheet(lines: pd.DataFrame, month: str, groups: list[dict], fallback: str) -> dict:
    """Everything the sheet shows for `month` ('YYYY-MM').

    `lines` is every classified line of the user (all months, for the "usual"
    comparison), with `value` and `alt_value`.
    """
    spending_all = lines[lines["kind"] == SPENDING]
    usual, usual_months = _usual(spending_all, month,
                                 group_names(spending_all["category"], groups, fallback))

    in_month = periods(lines, "%Y-%m") == month
    scoped = lines[in_month]
    income = _section(scoped[scoped["kind"] == INCOME], +1)
    savings = _section(scoped[scoped["kind"] == INVESTMENT], -1)

    spending = scoped[scoped["kind"] == SPENDING]
    spending_groups = group_names(spending["category"], groups, fallback)
    group_rows = []
    for g in groups:
        section = _section(spending[spending_groups == g["name"]], -1)
        group_rows.append({
            "name": g["name"],
            "icon": g["icon"],
            "color": g["color"],
            "member_categories": g["categories"],
            "usual": usual.get(g["name"], 0.0) if usual_months else None,
            **section,
        })

    expenses = -spending["value"].sum()
    expenses_alt = -spending["alt_value"].sum()
    remaining = income["total"] - expenses
    remaining_alt = income["total_alt"] - expenses_alt
    totals = {
        "income": income["total"], "income_alt": income["total_alt"],
        "expenses": _r(expenses), "expenses_alt": _r(expenses_alt),
        "remaining": _r(remaining), "remaining_alt": _r(remaining_alt),
        "remaining_pct": round(remaining / income["total"] * 100, 2) if income["total"] > 0 else None,
        "invested": savings["total"], "invested_alt": savings["total_alt"],
        "left_over": _r(remaining - savings["total"]),
        "left_over_alt": _r(remaining_alt - savings["total_alt"]),
    }
    return {
        "last_date": scoped["date"].max().date().isoformat() if not scoped.empty else None,
        "usual_months": usual_months,
        "totals": totals,
        "income": income,
        "savings": savings,
        "groups": group_rows,
    }
