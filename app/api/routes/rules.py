from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.security import verify_api_key
from app.services.rules import get_rules, add_rule, delete_rule, preview_rule_rerun, apply_rule_rerun

router = APIRouter()

class RuleCreate(BaseModel):
    category: str
    keyword: str

@router.get("/api/rules")
async def list_rules():
    return get_rules()

@router.post("/api/rules")
async def create_rule(payload: RuleCreate, api_key: str = Depends(verify_api_key)):
    rule_id = add_rule(payload.category, payload.keyword)
    return {"id": rule_id, "category": payload.category, "keyword": payload.keyword}

@router.delete("/api/rules/{rule_id}")
async def remove_rule(rule_id: int, api_key: str = Depends(verify_api_key)):
    if not delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "deleted"}

@router.get("/api/rules/preview-rerun")
async def preview_rerun():
    return preview_rule_rerun()

@router.post("/api/rules/apply-rerun")
async def apply_rerun(api_key: str = Depends(verify_api_key)):
    count = apply_rule_rerun()
    return {"updated": count}