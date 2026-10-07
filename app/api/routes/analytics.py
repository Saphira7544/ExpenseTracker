
from fastapi import APIRouter, Depends
from typing import Optional
from app.core.dependencies import get_current_user
from app.services.analytics import (
    get_overview_bundle,
    get_monthly_bundle,
    get_networth_analytics_bundle,
)

router = APIRouter()


@router.get("/api/analytics/overview")
def analytics_overview(
    year: Optional[str] = None,  # 'YYYY' or 'all' — defaults to 'all'
    currency: Optional[str] = None,  # 'CHF' / 'EUR' — defaults to the user's display currency
    user: dict = Depends(get_current_user),
):
    return get_overview_bundle(user["id"], year, currency)


@router.get("/api/analytics/monthly")
def analytics_monthly(
    month: Optional[str] = None,  # 'YYYY-MM' — defaults to most recent month with data
    currency: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    return get_monthly_bundle(user["id"], month, currency)


@router.get("/api/analytics/networth-charts")
def analytics_networth_charts(
    user: dict = Depends(get_current_user),
):
    return get_networth_analytics_bundle(user["id"])
