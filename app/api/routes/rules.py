from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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

@router.get("/api/rules")
async def list_rules(user: dict = Depends(get_current_user)):
    return get_rules(user["id"])

@router.post("/api/rules")
async def create_rule(payload: RuleCreate, user: dict = Depends(get_current_user)):
    rule_id = add_rule(payload.category, payload.keyword, user["id"])
    return {"id": rule_id, "category": payload.category, "keyword": payload.keyword}

@router.delete("/api/rules/{rule_id}")
async def remove_rule(rule_id: int, user: dict = Depends(get_current_user)):
    if not delete_rule(rule_id, user["id"]):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "deleted"}

@router.get("/api/rules/preview-rerun")
async def preview_rerun(user: dict = Depends(get_current_user)):
    return preview_rule_rerun(user["id"])

@router.post("/api/rules/apply-rerun")
async def apply_rerun(user: dict = Depends(get_current_user)):
    count = apply_rule_rerun(user["id"])
    return {"updated": count}