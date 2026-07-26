from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from app.core.security import verify_api_key
from app.services.transactions import (
    get_transactions, get_categories, get_accounts, update_transaction_category,
    get_transaction_by_id, save_splits, get_splits_for_transaction, undo_split,
    count_transactions, bulk_update_category, revert_to_auto
)

router = APIRouter()

class BulkCategoryUpdate(BaseModel):
    transaction_ids: list[str]
    category: str

@router.patch("/api/transactions/bulk-category")
async def bulk_category_update(payload: BulkCategoryUpdate, api_key: str = Depends(verify_api_key)):
    updated = bulk_update_category(payload.transaction_ids, payload.category)
    return {"updated": updated}

class CategoryUpdate(BaseModel):
    category: str

@router.get("/api/transactions")
async def list_transactions(
    account: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    amount_sign: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    split_status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    return get_transactions(account, category, search, date_from, date_to,
                             amount_sign, min_amount, max_amount, split_status, limit, offset)

@router.get("/api/transactions/filters")
async def filters():
    return {"categories": get_categories(), "accounts": get_accounts()}

@router.patch("/api/transactions/{transaction_id}")
async def update_category(transaction_id: str, payload: CategoryUpdate, api_key: str = Depends(verify_api_key)):
    updated = update_transaction_category(transaction_id, payload.category)
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"transactionId": transaction_id, "category": payload.category}


# Split-related endpoints
class SplitItem(BaseModel):
    category: str
    amount: float
    note: Optional[str] = None

class SplitRequest(BaseModel):
    splits: list[SplitItem]
    remainder_category: Optional[str] = "Other"

@router.post("/api/transactions/{transaction_id}/split")
async def split_transaction(transaction_id: str, payload: SplitRequest, api_key: str = Depends(verify_api_key)):
    original = get_transaction_by_id(transaction_id)
    if not original:
        raise HTTPException(status_code=404, detail="Transaction not found")

    total_split = sum(s.amount for s in payload.splits)
    if total_split > abs(original["amount"]) + 0.01:
        raise HTTPException(status_code=400, detail="Split amounts exceed transaction total")

    save_splits(transaction_id, [s.dict() for s in payload.splits], payload.remainder_category)
    return {"status": "ok", "transactionId": transaction_id}

@router.delete("/api/transactions/{transaction_id}/split")
async def remove_split(transaction_id: str, api_key: str = Depends(verify_api_key)):
    undo_split(transaction_id)
    return {"status": "ok", "transactionId": transaction_id}



@router.get("/api/transactions/count")
async def transactions_count(
    account: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    amount_sign: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    split_status: Optional[str] = None,
):
    total = count_transactions(account, category, search, date_from, date_to,
                                amount_sign, min_amount, max_amount, split_status)
    return {"total": total}

@router.post("/api/transactions/{transaction_id}/revert-auto")
async def revert_category(transaction_id: str, api_key: str = Depends(verify_api_key)):
    reverted = revert_to_auto(transaction_id)
    if not reverted:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"transactionId": transaction_id, "is_manual_category": False}