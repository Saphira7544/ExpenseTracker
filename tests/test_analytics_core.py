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


def test_negative_split_parts_go_the_other_way():
    # +100 repayment: +130 groceries they owed me, -30 my share of a dinner they paid
    lines = core.build_lines(
        tx([("r", "2026-03-31", "Repayment", "Split", 100.0, "CHF")]),
        splits([("r", "Groceries", 130.0), ("r", "Restaurants/Bars", -30.0)]),
    )
    assert dict(zip(lines["category"], lines["amount"])) == {"Groceries": 130.0, "Restaurants/Bars": -30.0}


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


def test_category_heatmap_has_every_month_and_nets_each_category():
    rows = SHARED_MONTH + [("t8", "2026-05-02", "Coop", "Groceries", -60.0, "CHF")]
    data = core.category_heatmap(prepared(rows, SHARED_SPLITS))
    assert data["periods"] == ["2026-03", "2026-04", "2026-05"]   # April has no spending but keeps its column
    by_cat = {r["category"]: r for r in data["rows"]}
    assert [r["category"] for r in data["rows"]] == ["Groceries", "Shopping", "Transfers"]   # biggest first
    assert by_cat["Groceries"]["values"] == {"2026-03": 90.0, "2026-05": 60.0}
    assert by_cat["Groceries"]["average"] == 50.0
    assert by_cat["Transfers"]["values"] == {}          # paid back in full: nets to zero
    assert data["total"] == {"2026-03": 140.0, "2026-05": 60.0}


def test_recategorizing_out_of_other_changes_the_heatmap():
    rows = [
        ("a", "2026-03-01", "Coop", "Groceries", -300.0, "CHF"),
        ("b", "2026-03-02", "Misc 1", "Other", -200.0, "CHF"),
        ("c", "2026-03-03", "Misc 2", "Other", -100.0, "CHF"),
    ]
    before = {r["category"]: r["total"] for r in core.category_heatmap(prepared(rows))["rows"]}
    assert before["Other"] == 300.0
    rows[2] = ("c", "2026-03-03", "Misc 2", "Entertainment", -100.0, "CHF")   # requalified
    after = {r["category"]: r["total"] for r in core.category_heatmap(prepared(rows))["rows"]}
    assert after == {"Groceries": 300.0, "Other": 200.0, "Entertainment": 100.0}


def test_spending_lines_keep_split_notes_and_sign():
    lines = core.build_lines(
        tx(SHARED_MONTH),
        pd.DataFrame([("t2", "Groceries", 50.0, "my half"), ("t2", "Transfers", 50.0, None)],
                     columns=core.SPLIT_COLUMNS + ["note"]),
    )
    lines["value"] = lines["amount"]
    out = core.spending_lines(core.classify(lines, ("Salary",), ("Investments",)))
    assert [l["date"] for l in out] == sorted(l["date"] for l in out)
    assert {"description": "Migros", "category": "Groceries", "spent": 50.0, "note": "my half"}.items()         <= next(l for l in out if l["category"] == "Groceries" and l["description"] == "Migros").items()
    assert next(l for l in out if l["description"] == "Zalando refund")["spent"] == -30.0   # money back
    assert all(l["description"] not in ("Salary ACME", "Broker") for l in out)


def test_category_history_covers_the_months_before():
    rows = SHARED_MONTH + [("t8", "2025-12-02", "Coop", "Groceries", -60.0, "CHF"),
                           ("t9", "2026-04-02", "Coop", "Groceries", -70.0, "CHF")]   # after: not included
    h = core.category_history(prepared(rows, SHARED_SPLITS), "2026-03", months=4)
    assert h["months"] == ["2025-12", "2026-01", "2026-02", "2026-03"]
    assert h["by_category"]["Groceries"] == {"2025-12": 60.0, "2026-03": 90.0}
    assert h["total"] == {"2025-12": 60.0, "2026-03": 140.0}


def test_empty_data():
    lines = prepared([])
    assert core.totals(lines)["income"] == 0.0
    assert core.trend(lines, "%Y") == []
    assert core.category_heatmap(lines) == {"periods": [], "rows": [], "total": {}}
    assert core.spending_lines(lines) == []
    assert core.month_summary(lines, 0)["biggest_expense_description"] is None


def test_ignored_categories_are_left_out_of_every_total():
    rows = SHARED_MONTH + [
        ("t9", "2026-03-20", "Transfer to my Revolut", "Investments", -10000.0, "CHF"),  # money going to be invested
        ("t10", "2026-03-21", "Exchanged to EUR", "Internal", -7476.7, "CHF"),          # same money, converted
    ]
    with_internal = prepared(rows, SHARED_SPLITS, investment=("Investments",))
    lines = core.classify(with_internal, ("Salary",), ("Investments",), ("Internal",))
    t = core.totals(lines)
    assert t["expenses"] == -140.0          # the exchange is not spending
    assert t["invested"] == 11000.0         # 1000 + 10000, counted once
    assert t["savings_rate"] == pytest.approx(97.2)
    assert "Internal" not in {r["category"] for r in core.category_breakdown(lines)}
    assert all(r["description"] != "Exchanged to EUR" for r in core.spending_lines(lines))

    # without the ignored role the same exchange would count as spending
    unignored = core.classify(with_internal, ("Salary",), ("Investments",), ())
    assert core.totals(unignored)["expenses"] == pytest.approx(-140.0 - 7476.7)
