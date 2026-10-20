from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from app.services.categories import unknown_categories
from app.core.dependencies import get_current_user
from app.services.rules import (
    get_rules,
    add_rule,
    delete_rule,
    preview_rule_rerun,
    apply_rule_rerun,
)

router = APIRouter()

class RuleCreate(BaseModel):
    category: str
    keyword: str

    @field_validator("keyword")
    @classmethod
    def _non_empty_keyword(cls, value: str) -> str:
        # An empty keyword would match every transaction.
        if not value.strip():
            raise ValueError("Keyword must not be empty")
        return value

@router.get("/api/rules")
def list_rules(user: dict = Depends(get_current_user)):
    return get_rules(user["id"])

@router.post("/api/rules")
def create_rule(payload: RuleCreate, user: dict = Depends(get_current_user)):
    if unknown_categories(user["id"], [payload.category]):
        raise HTTPException(status_code=422, detail=f"Unknown category: {payload.category}")
    rule_id = add_rule(payload.category, payload.keyword, user["id"])
    return {"id": rule_id, "category": payload.category, "keyword": payload.keyword}

@router.delete("/api/rules/{rule_id}")
def remove_rule(rule_id: int, user: dict = Depends(get_current_user)):
    if not delete_rule(rule_id, user["id"]):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "deleted"}

@router.get("/api/rules/preview-rerun")
def preview_rerun(user: dict = Depends(get_current_user)):
    return preview_rule_rerun(user["id"])

@router.post("/api/rules/apply-rerun")
def apply_rerun(user: dict = Depends(get_current_user)):
    count = apply_rule_rerun(user["id"])
    return {"updated": count}