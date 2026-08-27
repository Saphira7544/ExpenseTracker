from fastapi import APIRouter, Depends
from typing import Optional
from app.core.dependencies import get_current_user
from app.services.analytics import get_dashboard_bundle

router = APIRouter()


@router.get("/api/analytics/dashboard")
async def analytics_dashboard(
    month: Optional[str] = None,  # 'YYYY-MM', optional — defaults to most recent month with data
    user: dict = Depends(get_current_user),
):
    return get_dashboard_bundle(user["id"], month)