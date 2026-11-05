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


AVERAGE_MONTHS = [
    ("j1", "2026-01-25", "Salary", "Salary", 5000.0, "CHF"),
    ("j2", "2026-01-10", "Rent", "Rents", -2000.0, "CHF"),
    # February: nothing at all, still a month that counts
    ("m1", "2026-03-25", "Salary", "Salary", 5000.0, "CHF"),
    ("m2", "2026-03-10", "Rent", "Rents", -2000.0, "CHF"),
    ("m3", "2026-03-20", "Broker", "Investments", -900.0, "CHF"),
    ("o1", "2026-10-02", "Coop", "Groceries", -50.0, "CHF"),  # current month: not finished
]


def test_monthly_average_uses_complete_months_only():
    avg = core.monthly_average(prepared(AVERAGE_MONTHS), "2026-10")
    assert (avg["months"], avg["from"], avg["to"]) == (3, "2026-01", "2026-03")
    assert avg["left_out"] == ["2026-10"]
    assert avg["income"] == round(10000 / 3, 2)
    assert avg["expenses"] == round(-4000 / 3, 2)
    assert avg["invested"] == 300.0
    assert avg["net"] == 2000.0
    assert avg["savings_rate"] == 60.0


def test_monthly_average_is_none_without_a_complete_month():
    assert core.monthly_average(prepared(AVERAGE_MONTHS[-1:]), "2026-10") is None
    assert core.monthly_average(prepared(AVERAGE_MONTHS).iloc[0:0], "2026-10") is None


TRIP_MONTH = [
    ("s", "2026-05-25", "Salary", "Salary", 5000.0, "CHF"),
    ("r", "2026-05-01", "Rent", "Rents", -2000.0, "CHF"),
    ("f", "2026-05-10", "Flight", "Travel", -800.0, "CHF"),
    ("h", "2026-05-12", "Hotel", "Travel", -500.0, "CHF"),
    ("p", "2026-05-20", "Friend pays hotel half", "Travel", 250.0, "CHF"),
]


def trip_lines():
    lines = core.build_lines(tx(TRIP_MONTH), splits([]))
    lines["value"] = lines["amount"]
    return core.classify(lines, ["Salary"], ["Investments"], ["Internal"], ["Travel"])


def test_occasional_spending_is_shown_apart_but_still_counts():
    t = core.totals(trip_lines())
    assert t["expenses"] == -3050.0               # trips are still expenses
    assert t["occasional"] == -1050.0             # net of the friend's repayment
    assert t["regular_expenses"] == -2000.0
    assert (t["net_regular"], t["net"]) == (3000.0, 1950.0)
    assert (t["savings_rate_regular"], t["savings_rate"]) == (60.0, 39.0)


def test_without_occasional_categories_everything_is_regular():
    t = core.totals(prepared(TRIP_MONTH))
    assert t["occasional"] == 0.0 and t["regular_expenses"] == t["expenses"]


def test_biggest_trip_expenses_leave_out_money_back():
    assert [l["description"] for l in core.occasional_lines(trip_lines())] == ["Flight", "Hotel"]


def month_rows(year, income, spent):
    """One salary and one expense per month; income/spent are {month: amount}."""
    rows = []
    for m, amount in income.items():
        rows.append((f"i{year}{m}", f"{year}-{m:02d}-25", "Salary", "Salary", float(amount), "CHF"))
    for m, amount in spent.items():
        rows.append((f"s{year}{m}", f"{year}-{m:02d}-10", "Rent", "Rents", -float(amount), "CHF"))
    return rows


LAST_YEAR = month_rows(2025, {m: 1000 for m in range(1, 13)} | {12: 3000}, {1: 500})
THIS_YEAR = month_rows(2026, {m: 1000 for m in range(1, 11)}, {m: 600 for m in range(1, 11)})


def test_projection_uses_last_years_income_and_this_years_average_spending():
    p = core.year_end_projection(prepared(LAST_YEAR + THIS_YEAR), "2026-11")
    assert (p["year"], p["months_known"], p["months_left"]) == ("2026", 10, 2)
    assert p["income"] == 10000 + 1000 + 3000          # December's bigger salary counts
    assert p["expenses"] == -7200                      # 600 a month for all 12
    assert p["net"] == 6800
    assert p["savings_rate"] == 48.6
    assert p["income_from_last_year"] is True


def test_projection_ignores_the_month_in_progress():
    november = month_rows(2026, {11: 9999}, {11: 9999})
    with_november = core.year_end_projection(prepared(LAST_YEAR + THIS_YEAR + november), "2026-11")
    assert with_november == core.year_end_projection(prepared(LAST_YEAR + THIS_YEAR), "2026-11")


def test_projection_uses_this_years_average_income_without_a_last_year():
    p = core.year_end_projection(prepared(THIS_YEAR), "2026-11")
    assert p["income"] == 12000 and p["income_from_last_year"] is False


def test_projection_needs_six_complete_months():
    five = month_rows(2026, {m: 1000 for m in range(1, 6)}, {})
    assert core.year_end_projection(prepared(five), "2026-06") is None
    six = month_rows(2026, {m: 1000 for m in range(1, 7)}, {})
    assert core.year_end_projection(prepared(six), "2026-07") is not None


def test_projection_treats_months_after_the_last_import_as_still_to_come():
    # Today is November but nothing was imported after June: July to October are projected too.
    six = month_rows(2026, {m: 1000 for m in range(1, 7)}, {m: 100 for m in range(1, 7)})
    p = core.year_end_projection(prepared(six), "2026-11")
    assert (p["months_known"], p["months_left"]) == (6, 6)


def test_projection_with_trips_says_what_it_would_be_before_them():
    trip = [("t", "2026-05-10", "Flight", "Travel", -600.0, "CHF")]
    lines = core.build_lines(tx(LAST_YEAR + THIS_YEAR + trip), splits([]))
    lines["value"] = lines["amount"]
    p = core.year_end_projection(core.classify(lines, ["Salary"], ["Investments"], ["Internal"], ["Travel"]), "2026-11")
    assert p["expenses"] == -7920                      # (6000 + 600) a year-to-date average of 660 a month
    assert p["net_regular"] == 6800                    # the same without the trip
    assert p["savings_rate_regular"] == 48.6


def test_investing_never_changes_the_savings_rate():
    without = core.totals(prepared(AVERAGE_MONTHS[:4]))    # 5000 + 5000 in, 4000 out
    invested = core.totals(prepared(AVERAGE_MONTHS[:5]))   # the same plus 900 invested
    assert without["savings_rate"] == invested["savings_rate"] == 60.0


def counted_lines(rows, split_rows=()):
    transactions = pd.DataFrame(rows, columns=core.TX_COLUMNS + ["counts_in"])
    parts = pd.DataFrame(list(split_rows), columns=core.SPLIT_COLUMNS + ["counts_in"])
    lines = core.build_lines(transactions, parts)
    lines["value"] = lines["amount"]
    return core.classify(lines, ["Salary"], ["Investments"], ["Internal"])


def test_a_transaction_counts_in_its_month_and_keeps_its_real_date():
    lines = counted_lines([("s", "2025-12-19", "Salary", "Salary", 5000.0, "CHF", "2026-01")])
    assert lines["date"].iloc[0] == pd.Timestamp("2026-01-19")
    assert lines["paid_on"].iloc[0] == pd.Timestamp("2025-12-19")
    assert [r["period"] for r in core.trend(lines, "%Y-%m")] == ["2026-01"]


def test_without_a_month_nothing_moves():
    lines = counted_lines([("s", "2025-12-19", "Salary", "Salary", 5000.0, "CHF", None)])
    assert lines["date"].iloc[0] == lines["paid_on"].iloc[0] == pd.Timestamp("2025-12-19")


def test_moving_to_a_shorter_month_uses_its_last_day():
    assert core.counted_date(pd.Timestamp("2026-01-31"), "2026-02") == pd.Timestamp("2026-02-28")
    assert core.counted_date(pd.Timestamp("2026-03-31"), "2024-02") == pd.Timestamp("2024-02-29")


def test_one_settlement_can_pay_two_months_of_rent():
    lines = counted_lines(
        [("a", "2025-08-04", "Francisco", "Split", 2509.0, "CHF", None),
         ("r1", "2025-07-28", "Rent", "Rents", -2240.0, "CHF", None),
         ("r2", "2025-08-29", "Rent", "Rents", -2240.0, "CHF", None)],
        [("a", "Rents", 1223.5, "2025-07"), ("a", "Rents", 1223.5, None), ("a", "Groceries", 62.0, None)],
    )
    per_month = {r["period"]: r["expenses"] for r in core.trend(lines, "%Y-%m")}
    assert per_month == {"2025-07": -1016.5, "2025-08": -954.5}   # August also has 62 back on groceries
    moved = lines[(lines["transaction_id"] == "a") & (lines["date"] < "2025-08-01")]
    assert list(moved["paid_on"]) == [pd.Timestamp("2025-08-04")]
    assert sum(core.totals(lines)[k] for k in ("expenses",)) == -1971.0   # the year's total doesn't change


def test_a_part_follows_its_transaction_unless_it_says_otherwise():
    lines = counted_lines(
        [("a", "2025-08-04", "Francisco", "Split", 100.0, "CHF", "2025-09")],
        [("a", "Rents", 60.0, None), ("a", "Groceries", 40.0, "2025-07")],
    )
    months = {r.category: r.date.strftime("%Y-%m") for r in lines.itertuples()}
    assert months == {"Rents": "2025-09", "Groceries": "2025-07"}


def test_lines_on_the_page_carry_the_real_date_too():
    lines = counted_lines([("h", "2026-09-01", "Helsana", "Health", -314.55, "CHF", "2026-08")])
    [line] = core.spending_lines(lines)
    assert (line["date"], line["paid_on"]) == ("2026-08-01", "2026-09-01")


def test_exchange_rates_use_the_real_date(monkeypatch):
    from app.services import analytics
    transactions = pd.DataFrame(
        [("s", pd.Timestamp("2025-12-19"), "Salary", "Salary", 100.0, "EUR", "2026-01")],
        columns=core.TX_COLUMNS + ["counts_in"],
    )
    parts = pd.DataFrame([], columns=core.SPLIT_COLUMNS + ["note", "counts_in"])
    seen = {}

    def convert(frame, target, rates):
        seen["date"] = frame["date"].iloc[0]
        return frame["amount"], []

    monkeypatch.setattr(analytics, "_load_frames", lambda uid: (transactions, parts))
    monkeypatch.setattr(analytics, "get_settings", lambda uid: {
        "display_currency": "CHF", "income_categories": ["Salary"], "investment_categories": [],
        "ignored_categories": [], "occasional_categories": [],
    })
    monkeypatch.setattr(analytics.fx, "ensure_rates", lambda currencies, start: seen.setdefault("start", start))
    monkeypatch.setattr(analytics.fx, "load_rates", lambda currencies: None)
    monkeypatch.setattr(analytics.fx, "convert", convert)
    lines, _, _ = analytics._prepare(7, "CHF")
    assert seen["date"] == pd.Timestamp("2025-12-19")
    assert str(seen["start"]) == "2025-12-19"
    assert lines["date"].iloc[0] == pd.Timestamp("2026-01-19")
