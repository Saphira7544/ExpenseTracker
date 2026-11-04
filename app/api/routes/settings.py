from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from app.services.categories import categories_for
from app.core.dependencies import get_current_user
from app.services.ai_settings import key_problem, key_status, save_api_key, delete_api_key
from categorizers.openAI import check_key
from app.services.settings import (
    SUPPORTED_DISPLAY_CURRENCIES,
    available_banks,
    get_settings,
    validate_settings,
    save_settings,
    list_exclusions,
    add_exclusion,
    delete_exclusion,
)

router = APIRouter()


class SettingsUpdate(BaseModel):
    # All optional: the currency toggle on the dashboards only sends display_currency.
    display_currency: Optional[str] = None
    income_categories: Optional[list[str]] = None
    investment_categories: Optional[list[str]] = None
    ignored_categories: Optional[list[str]] = None
    occasional_categories: Optional[list[str]] = None


class AiKeySave(BaseModel):
    # Checked in the route, not with a validator: FastAPI's validation errors
    # echo the submitted value back, and the key must never be sent back.
    api_key: str


class ExclusionCreate(BaseModel):
    bank: Optional[str] = None  # None = all banks
    pattern: str

    @field_validator("pattern")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        # An empty pattern would skip every transaction in the file.
        if not value.strip():
            raise ValueError("Pattern must not be empty")
        return value.strip()


@router.get("/api/settings")
def read_settings(user: dict = Depends(get_current_user)):
    return {
        **get_settings(user["id"]),
        "exclusions": list_exclusions(user["id"]),
        "banks": available_banks(user["id"]),
        "categories": categories_for(user["id"]),
        "available_currencies": SUPPORTED_DISPLAY_CURRENCIES,
    }


@router.patch("/api/settings")
def update_settings(payload: SettingsUpdate, user: dict = Depends(get_current_user)):
    settings = {**get_settings(user["id"]), **payload.model_dump(exclude_none=True)}
    problem = validate_settings(settings, categories_for(user["id"]))
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    save_settings(user["id"], settings)
    return settings


@router.get("/api/settings/ai-key")
def read_ai_key_status(user: dict = Depends(get_current_user)):
    return key_status(user["id"])


@router.put("/api/settings/ai-key")
def store_ai_key(payload: AiKeySave, user: dict = Depends(get_current_user)):
    api_key = payload.api_key.strip()
    problem = key_problem(api_key)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    usable, warning = check_key(api_key)
    if not usable:
        raise HTTPException(status_code=400, detail=warning)
    save_api_key(user["id"], api_key)
    return {**key_status(user["id"]), "warning": warning}


@router.delete("/api/settings/ai-key")
def remove_ai_key(user: dict = Depends(get_current_user)):
    delete_api_key(user["id"])
    return key_status(user["id"])


@router.post("/api/settings/exclusions")
def create_exclusion(payload: ExclusionCreate, user: dict = Depends(get_current_user)):
    if payload.bank is not None and payload.bank not in available_banks(user["id"]):
        raise HTTPException(status_code=400, detail="Unknown bank")
    exclusion_id = add_exclusion(user["id"], payload.bank, payload.pattern)
    return {"id": exclusion_id, "bank": payload.bank, "pattern": payload.pattern}


@router.delete("/api/settings/exclusions/{exclusion_id}")
def remove_exclusion(exclusion_id: int, user: dict = Depends(get_current_user)):
    if not delete_exclusion(user["id"], exclusion_id):
        raise HTTPException(status_code=404, detail="Exclusion not found")
    return {"status": "deleted"}
