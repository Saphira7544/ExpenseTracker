"""Monthly Sheet page (/sheet): loading and conversion; the maths is in sheet_core."""
from datetime import date

import pandas as pd

from app.core.categories import SHEET_FALLBACK_GROUP
from app.services.categories import sheet_groups_for
from app.services import fx, sheet_core
from app.services.analytics import _prepare
from app.services.settings import SUPPORTED_DISPLAY_CURRENCIES


def _other_currency(currency: str) -> str:
    """The sheet shows every total in the display currency and in this one."""
    return next(c for c in SUPPORTED_DISPLAY_CURRENCIES if c != currency)


def _month_end(month: str) -> date:
    return pd.Period(month, freq="M").end_time.date()


def get_sheet_bundle(user_id: int, month: str | None = None, currency: str | None = None) -> dict:
    lines, tx, meta = _prepare(user_id, currency)
    alt = _other_currency(meta["currency"])
    meta["alt_currency"] = alt

    tx_months = tx["date"].dt.strftime("%Y-%m")
    available_months = sorted(set(tx_months), reverse=True)
    selected_month = month if month in available_months else (available_months[0] if available_months else None)
    if not selected_month:
        return {"available_months": [], "selected_month": None, "sheet": None, "rate": None, **meta}

    if lines.empty:
        lines["alt_value"] = pd.Series(dtype=float)
    else:
        currencies = set(lines["currency"]) | {alt}
        fx.ensure_rates(currencies, lines["date"].min().date())
        lines["alt_value"], missing = fx.convert(lines, alt, fx.load_rates(currencies))
        lines = lines.dropna(subset=["alt_value"])
        meta["fx_missing"] = sorted(set(meta["fx_missing"]) | set(missing))

    sheet = sheet_core.month_sheet(lines, selected_month, sheet_groups_for(user_id), SHEET_FALLBACK_GROUP)
    # The sheet's "conversion rate" box: the rate on the last day of the
    # month (or today, for the current month).
    rate_day = min(_month_end(selected_month), date.today())
    rate = fx.rate_on(meta["currency"], alt, rate_day)
    return {
        "available_months": available_months,
        "selected_month": selected_month,
        "sheet": sheet,
        "rate": rate,
        **meta,
    }
