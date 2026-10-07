import pandas as pd
import pytest

from app.services import analytics_core as core


def tx(rows):
    return pd.DataFrame(rows, columns=core.TX_COLUMNS)


def splits(rows):
    return pd.DataFrame(rows, columns=core.SPLIT_COLUMNS)


def prepared(transactions, split_rows=(), income=("Salary",), investment=("Investments",)):
    lines = core.build_lines(tx(transactions), splits(list(split_rows)))
    lines["value"] = lines["amount"]  # single currency: no conversion
    return core.classify(lines, income, investment)


SHARED_MONTH = [
    ("t1", "2026-03-01", "Salary ACME", "Salary", 5000.0, "CHF"),
    ("t2", "2026-03-05", "Migros", "Split", -100.0, "CHF"),             # shared groceries
    ("t3", "2026-03-10", "Coop", "Groceries", -40.0, "CHF"),
    ("t4", "2026-03-31", "Boyfriend TWINT", "Transfers", 50.0, "CHF"),  # pays his half back
    ("t5", "2026-03-15", "Zalando refund", "Shopping", 30.0, "CHF"),
    ("t6", "2026-03-12", "Zalando", "Shopping", -80.0, "CHF"),
    ("t7", "2026-03-20", "Broker", "Investments", -1000.0, "CHF"),
]
SHARED_SPLITS = [("t2", "Groceries", 50.0), ("t2", "Transfers", 50.0)]


def test_split_transaction_is_replaced_by_its_parts_with_parent_sign():
    lines = core.build_lines(tx(SHARED_MONTH), splits(SHARED_SPLITS))
    parts = lines[lines["transaction_id"] == "t2"].sort_values("category")
    assert list(parts["category"]) == ["Groceries", "Transfers"]
    assert list(parts["amount"]) == [-50.0, -50.0]
    assert "Split" not in set(lines["category"])


def test_split_without_rows_is_kept_rather_than_lost():
    lines = core.build_lines(tx([("t1", "2026-03-01", "x", "Split", -10.0, "CHF")]), splits([]))
    assert list(lines["amount"]) == [-10.0]


def test_repayment_and_refund_net_against_their_category_not_income():
    lines = prepared(SHARED_MONTH, SHARED_SPLITS)
    breakdown = {r["category"]: r["total"] for r in core.category_breakdown(lines)}
    assert breakdown == {"Groceries": 90.0, "Shopping": 50.0}  # Transfers nets to 0 and is dropped

    t = core.totals(lines)
    assert t["income"] == 5000.0          # repayment and refund are NOT income
    assert t["expenses"] == -140.0        # 90 groceries + 50 shopping
    assert t["invested"] == 1000.0
    assert t["net"] == 4860.0
    assert t["savings_rate"] == pytest.approx(97.2)


def test_income_and_investment_categories_come_from_settings():
    lines = prepared(SHARED_MONTH, SHARED_SPLITS, income=("Salary", "Transfers"), investment=())
    t = core.totals(lines)
    assert t["income"] == 5000.0  # Transfers is income now: -50 split part + 50 repayment
    assert t["invested"] == 0.0
    assert "Investments" in {r["category"] for r in core.category_breakdown(lines)}


def test_month_summary_uses_split_parts_for_biggest_and_average():
    lines = prepared(SHARED_MONTH, SHARED_SPLITS)
    s = core.month_summary(lines, txn_count=7)
    assert s["txn_count"] == 7
    # outflows among spending lines: 50, 50 (split parts), 40, 80
    assert s["expense_count"] == 4
    assert s["avg_expense"] == 55.0
    assert s["biggest_expense_description"] == "Zalando"
    assert s["biggest_expense_amount"] == 80.0


def test_trend_groups_by_period():
    rows = SHARED_MONTH + [("t8", "2026-04-02", "Coop", "Groceries", -60.0, "CHF")]
    lines = prepared(rows, SHARED_SPLITS)
    trend = core.trend(lines, "%Y-%m")
    assert [r["period"] for r in trend] == ["2026-03", "2026-04"]
    assert trend[1]["expenses"] == -60.0
    assert core.trend(lines, "%Y")[0]["expenses"] == -200.0


def test_category_trend_keeps_top_categories_and_folds_the_rest():
    lines = prepared(SHARED_MONTH, SHARED_SPLITS)
    data = core.category_trend(lines, "%Y-%m", top_n=1)
    assert data["periods"] == ["2026-03"]
    assert data["series"]["Groceries"]["2026-03"] == 90.0
    assert data["series"]["Other"]["2026-03"] == 50.0  # Shopping 50 + Transfers 0


def test_top_merchants_and_daily_spend():
    lines = prepared(SHARED_MONTH, SHARED_SPLITS)
    merchants = core.top_merchants(lines)
    assert merchants[0] == {"description": "Migros", "total": 100.0, "occurrences": 2}
    daily = {d["date"]: d["total"] for d in core.daily_spend(lines)}
    assert daily["2026-03-05"] == 100.0
    assert daily["2026-03-31"] == -50.0  # repayment day shows as money coming back


def test_empty_data():
    lines = prepared([])
    assert core.totals(lines)["income"] == 0.0
    assert core.trend(lines, "%Y") == []
    assert core.category_trend(lines, "%Y") == {"periods": [], "series": {}}
    assert core.month_summary(lines, 0)["biggest_expense_description"] is None
