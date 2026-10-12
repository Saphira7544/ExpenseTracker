from fastapi import APIRouter, Depends
from typing import Optional
from app.core.dependencies import get_current_user
from app.services.sheet import get_sheet_bundle

router = APIRouter()


@router.get("/api/sheet")
def monthly_sheet(
    month: Optional[str] = None,  # 'YYYY-MM' — defaults to most recent month with data
    currency: Optional[str] = None,  # 'CHF' / 'EUR' — defaults to the user's display currency
    user: dict = Depends(get_current_user),
):
    return get_sheet_bundle(user["id"], month, currency)
