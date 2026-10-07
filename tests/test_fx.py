import pandas as pd
import pytest

from app.services import fx


RATES = pd.DataFrame(
    [("CHF", "2026-03-02", 0.95), ("CHF", "2026-03-04", 0.90), ("USD", "2026-03-02", 1.10)],
    columns=["currency", "rate_date", "per_eur"],
)
RATES["rate_date"] = pd.to_datetime(RATES["rate_date"])


def lines(rows):
    df = pd.DataFrame(rows, columns=["date", "amount", "currency"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_uses_rate_on_or_before_each_date():
    values, missing = fx.convert(lines([
        ("2026-03-02", 100.0, "EUR"),
        ("2026-03-03", 100.0, "EUR"),   # no rate that day -> previous rate
        ("2026-03-05", 100.0, "EUR"),
    ]), "CHF", RATES)
    assert list(values) == pytest.approx([95.0, 95.0, 90.0])
    assert missing == []


def test_dates_before_first_rate_use_earliest_rate():
    values, _ = fx.convert(lines([("2025-01-01", 100.0, "EUR")]), "CHF", RATES)
    assert values[0] == pytest.approx(95.0)


def test_chf_to_eur_and_cross_rates():
    values, _ = fx.convert(lines([
        ("2026-03-04", 90.0, "CHF"),
        ("2026-03-02", 110.0, "USD"),
    ]), "EUR", RATES)
    assert list(values) == pytest.approx([100.0, 100.0])


def test_same_currency_is_untouched_and_missing_rates_reported():
    values, missing = fx.convert(lines([
        ("2026-03-02", 42.0, "CHF"),
        ("2026-03-02", 10.0, "GBP"),
    ]), "CHF", RATES)
    assert values[0] == 42.0
    assert pd.isna(values[1])
    assert missing == ["GBP"]
