"""Exchange rates: daily ECB reference rates from frankfurter.app, cached in fx_rates.

Rates are stored as "units of currency per 1 EUR", so converting from A to B
on a given day is amount * per_eur(B) / per_eur(A), with per_eur(EUR) == 1.
"""
import logging
import time
from datetime import date, timedelta

import httpx
import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db.session import engine

logger = logging.getLogger(__name__)

FX_API = "https://api.frankfurter.app"
SOURCE_LABEL = "ECB reference rates (frankfurter.app)"

# Don't hit the API on every page load: new rates appear once per business
# day, and a failing API shouldn't be retried in a tight loop either.
REFRESH_INTERVAL_SECONDS = 6 * 3600
RETRY_AFTER_FAILURE_SECONDS = 10 * 60
_last_attempt: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Pure conversion helpers (no I/O)
# ---------------------------------------------------------------------------

def per_eur(dates: np.ndarray, currency: str, rates: pd.DataFrame) -> np.ndarray:
    """Rate on or before each date (earliest known rate for dates before the
    first one). NaN when the currency has no rates at all."""
    if currency == "EUR":
        return np.ones(len(dates))
    r = rates[rates["currency"] == currency].sort_values("rate_date")
    if r.empty:
        return np.full(len(dates), np.nan)
    rate_dates = r["rate_date"].to_numpy(dtype="datetime64[ns]")
    idx = np.searchsorted(rate_dates, dates.astype("datetime64[ns]"), side="right") - 1
    return r["per_eur"].to_numpy(dtype=float)[np.clip(idx, 0, None)]


def convert(lines: pd.DataFrame, target: str, rates: pd.DataFrame) -> tuple[pd.Series, list[str]]:
    """Convert lines[amount] (in lines[currency], on lines[date]) to `target`.

    Returns the converted values (NaN where no rate is known) and the
    currencies that could not be converted.
    """
    amounts = lines["amount"].to_numpy(dtype=float)
    dates = lines["date"].to_numpy(dtype="datetime64[ns]")
    values = np.full(len(lines), np.nan)
    target_rate = per_eur(dates, target, rates)
    missing = set()

    for currency in lines["currency"].unique():
        mask = (lines["currency"] == currency).to_numpy()
        if currency == target:
            values[mask] = amounts[mask]
            continue
        source_rate = per_eur(dates[mask], currency, rates)
        converted = amounts[mask] * target_rate[mask] / source_rate
        if np.isnan(converted).any():
            missing.add(currency if np.isnan(source_rate).any() else target)
        values[mask] = converted

    return pd.Series(values, index=lines.index), sorted(missing)


# ---------------------------------------------------------------------------
# Fetching and caching
# ---------------------------------------------------------------------------

def fetch_rates(start: date, end: date, currencies: list[str]) -> list[tuple[str, date, float]]:
    response = httpx.get(
        f"{FX_API}/{start.isoformat()}..{end.isoformat()}",
        params={"from": "EUR", "to": ",".join(currencies)},
        timeout=15,
        follow_redirects=True,
    )
    response.raise_for_status()
    return [
        (currency, date.fromisoformat(day), float(rate))
        for day, by_currency in response.json()["rates"].items()
        for currency, rate in by_currency.items()
    ]


def store_rates(rows: list[tuple[str, date, float]]) -> None:
    if not rows:
        return
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO fx_rates (currency, rate_date, per_eur)
                VALUES (:currency, :rate_date, :per_eur)
                ON CONFLICT (currency, rate_date) DO UPDATE SET per_eur = EXCLUDED.per_eur
            """),
            [{"currency": c, "rate_date": d, "per_eur": r} for c, d, r in rows]
        )
        conn.commit()


def ensure_rates(currencies: set[str], start: date) -> None:
    """Make sure fx_rates covers `currencies` from `start` until today.

    Best effort: on API failure it logs and keeps using whatever is cached.
    """
    needed = sorted(c for c in currencies if c and c != "EUR")
    if not needed:
        return

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT currency, MIN(rate_date), MAX(rate_date) FROM fx_rates
                WHERE currency = ANY(:currencies) GROUP BY currency
            """),
            {"currencies": needed}
        ).all()
    coverage = {r[0]: (r[1], r[2]) for r in rows}
    today = date.today()

    if any(c not in coverage or coverage[c][0] > start for c in needed):
        kind, fetch_from, interval = "backfill", start, RETRY_AFTER_FAILURE_SECONDS
    else:
        latest = min(coverage[c][1] for c in needed)
        if latest >= today:
            return
        kind, fetch_from, interval = "refresh", latest + timedelta(days=1), REFRESH_INTERVAL_SECONDS

    now = time.monotonic()
    if kind in _last_attempt and now - _last_attempt[kind] < interval:
        return
    _last_attempt[kind] = now

    try:
        store_rates(fetch_rates(fetch_from, today, needed))
    except Exception:
        logger.warning("Could not fetch exchange rates from %s", FX_API, exc_info=True)


def load_rates(currencies: set[str]) -> pd.DataFrame:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT currency, rate_date, per_eur FROM fx_rates
                WHERE currency = ANY(:currencies)
            """),
            {"currencies": sorted(currencies)}
        ).all()
    df = pd.DataFrame(rows, columns=["currency", "rate_date", "per_eur"])
    df["rate_date"] = pd.to_datetime(df["rate_date"])
    return df
