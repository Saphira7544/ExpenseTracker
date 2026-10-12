import pandas as pd

from app.services import analytics_core as core
from app.services import sheet_core

GROUPS = [
    {"name": "Food", "icon": "", "color": "", "categories": ["Groceries", "Restaurants/Bars"]},
    {"name": "Shopping", "icon": "", "color": "", "categories": ["Shopping"]},
    {"name": "Other", "icon": "", "color": "", "categories": ["Other", "Transfers"]},
]


def prepared(rows, split_rows=()):
    tx = pd.DataFrame(rows, columns=core.TX_COLUMNS)
    lines = core.build_lines(tx, pd.DataFrame(list(split_rows), columns=core.SPLIT_COLUMNS))
    lines["value"] = lines["amount"]          # display currency = CHF, no conversion
    lines["alt_value"] = lines["amount"] * 1.1  # "EUR"
    return core.classify(lines, ["Salary"], ["Investments"], ["Internal"])


MONTH = [
    ("t1", "2026-03-01", "Salary ACME", "Salary", 5000.0, "CHF"),
    ("t2", "2026-03-05", "Migros", "Split", -100.0, "CHF"),
    ("t3", "2026-03-10", "Pingo Doce", "Groceries", -40.0, "EUR"),
    ("t4", "2026-03-31", "Boyfriend TWINT", "Transfers", 50.0, "CHF"),
    ("t5", "2026-03-12", "Zalando", "Shopping", -80.0, "CHF"),
    ("t6", "2026-03-20", "Broker", "Investments", -1000.0, "CHF"),
    ("t7", "2026-03-21", "Own account", "Internal", -500.0, "CHF"),
    ("t8", "2026-03-22", "Mystery", "Sports", -30.0, "CHF"),  # in no group -> Other
    ("old", "2026-01-15", "Coop", "Groceries", -300.0, "CHF"),
]
SPLITS = [("t2", "Groceries", 50.0), ("t2", "Transfers", 50.0)]


def sheet():
    return sheet_core.month_sheet(prepared(MONTH, SPLITS), "2026-03", GROUPS, "Other")


def by_name(s):
    return {g["name"]: g for g in s["groups"]}


def test_spending_is_grouped_and_unlisted_categories_go_to_the_fallback():
    groups = by_name(sheet())
    assert groups["Food"]["total"] == 90.0
    assert {c["category"]: c["total"] for c in groups["Food"]["categories"]} == {"Groceries": 90.0}
    assert groups["Shopping"]["total"] == 80.0
    # Transfers -50 + 50 cancel out; Sports has no group of its own
    assert groups["Other"]["total"] == 30.0
    assert [c["category"] for c in groups["Other"]["categories"]] == ["Sports"]


def test_groups_keep_their_order_and_show_original_currencies():
    s = sheet()
    assert [g["name"] for g in s["groups"]] == ["Food", "Shopping", "Other"]
    assert by_name(s)["Food"]["by_currency"] == {"CHF": 50.0, "EUR": 40.0}


def test_totals_match_the_other_dashboards():
    s = sheet()
    t = s["totals"]
    expected = core.totals(prepared(MONTH, SPLITS).query("date >= '2026-03-01'"))
    assert t["income"] == expected["income"] == 5000.0
    assert t["expenses"] == -expected["expenses"] == 200.0
    assert t["remaining"] == expected["net"] == 4800.0
    assert t["remaining_pct"] == 96.0
    assert t["invested"] == 1000.0
    assert t["left_over"] == 3800.0
    assert t["expenses_alt"] == 220.0


def test_income_and_savings_sections_list_their_lines_as_positive_amounts():
    s = sheet()
    assert s["income"]["total"] == 5000.0
    assert [l["description"] for l in s["savings"]["lines"]] == ["Broker"]
    assert s["savings"]["lines"][0]["value"] == 1000.0
    assert s["last_date"] == "2026-03-31"


def test_lines_are_biggest_first_and_refunds_are_negative():
    other = by_name(sheet())["Other"]["lines"]
    assert [(l["category"], l["value"]) for l in other] == [("Transfers", 50.0), ("Sports", 30.0), ("Transfers", -50.0)]


def test_usual_averages_only_months_since_the_data_starts():
    s = sheet()
    # Data starts in January: the window is Jan + Feb, 300 groceries over 2 months.
    assert s["usual_months"] == 2
    assert by_name(s)["Food"]["usual"] == 150.0
    assert by_name(s)["Shopping"]["usual"] == 0.0


def test_first_month_has_no_usual():
    s = sheet_core.month_sheet(prepared(MONTH, SPLITS), "2026-01", GROUPS, "Other")
    assert s["usual_months"] == 0
    assert all(g["usual"] is None for g in s["groups"])
    assert s["totals"]["remaining_pct"] is None  # no income in January
