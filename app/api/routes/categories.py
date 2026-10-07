from fastapi import APIRouter, Depends
from app.core.dependencies import get_current_user
from app.core.categories import CATEGORIES

router = APIRouter()


@router.get("/api/categories")
def list_categories(user: dict = Depends(get_current_user)):
    return CATEGORIES