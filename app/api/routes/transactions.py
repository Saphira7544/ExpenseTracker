from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from app.core.categories import CATEGORIES
from app.core.dependencies import get_current_user
from app.services.transactions import (
    get_transactions, get_categories, get_accounts, update_transaction_category,
    get_transaction_by_id, save_splits, get_splits_for_transaction, undo_split,
    count_transactions, bulk_update_category, revert_to_auto
)

router = APIRouter()


def _known_category(value: str) -> str:
    # "Split" is set only by the split endpoint, never chosen directly.
    if value not in CATEGORIES:
        raise ValueError(f"Unknown category: {value}")
    return value


class BulkCategoryUpdate(BaseModel):
    transaction_ids: list[str]
    category: str
    _check_category = field_validator("category")(_known_category)

@router.patch("/api/transactions/bulk-category")
def bulk_category_update(
    payload: BulkCategoryUpdate,
    user: dict = Depends(get_current_user)
):
    updated = bulk_update_category(user["id"], payload.transaction_ids, payload.category)
    return {"updated": updated}

class CategoryUpdate(BaseModel):
    category: str
    _check_category = field_validator("category")(_known_category)

@router.get("/api/transactions")
def list_transactions(
    account: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    amount_sign: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    split_status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    return get_transactions(
        user["id"], account, category, search, date_from, date_to,
        amount_sign, min_amount, max_amount, split_status, limit, offset
    )

@router.get("/api/transactions/filters")
def filters(user: dict = Depends(get_current_user)):
    return {
        "categories": get_categories(user["id"]),
        "accounts": get_accounts(user["id"])
    }

@router.patch("/api/transactions/{transaction_id}")
def update_category(
    transaction_id: str,
    payload: CategoryUpdate,
    user: dict = Depends(get_current_user)
):
    updated = update_transaction_category(user["id"], transaction_id, payload.category)
    if not updated:
        existing = get_transaction_by_id(user["id"], transaction_id)
        if existing and existing["category"] == "Split":
            raise HTTPException(status_code=409, detail="Transaction is split; undo the split first")
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"transactionId": transaction_id, "category": payload.category}

class SplitItem(BaseModel):
    category: str
    amount: float
    note: Optional[str] = None
    _check_category = field_validator("category")(_known_category)

class SplitRequest(BaseModel):
    splits: list[SplitItem]
    remainder_category: str = "Other"
    _check_category = field_validator("remainder_category")(_known_category)

@router.post("/api/transactions/{transaction_id}/split")
def split_transaction(
    transaction_id: str,
    payload: SplitRequest,
    user: dict = Depends(get_current_user)
):
    original = get_transaction_by_id(user["id"], transaction_id)
    if not original:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if any(s.amount <= 0 for s in payload.splits):
        raise HTTPException(status_code=400, detail="Split amounts must be positive")

    total_split = sum(s.amount for s in payload.splits)
    if total_split > abs(original["amount"]) + 0.01:
        raise HTTPException(status_code=400, detail="Split amounts exceed transaction total")

    save_splits(user["id"], transaction_id, [s.model_dump() for s in payload.splits], payload.remainder_category)
    return {"status": "ok", "transactionId": transaction_id}

@router.delete("/api/transactions/{transaction_id}/split")
def remove_split(
    transaction_id: str,
    user: dict = Depends(get_current_user)
):
    undo_split(user["id"], transaction_id)
    return {"status": "ok", "transactionId": transaction_id}

@router.get("/api/transactions/count")
def transactions_count(
    account: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    amount_sign: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    split_status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    total = count_transactions(
        user["id"], account, category, search, date_from, date_to,
        amount_sign, min_amount, max_amount, split_status
    )
    return {"total": total}

@router.post("/api/transactions/{transaction_id}/revert-auto")
def revert_category(
    transaction_id: str,
    user: dict = Depends(get_current_user)
):
    reverted = revert_to_auto(user["id"], transaction_id)
    if not reverted:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"transactionId": transaction_id, "is_manual_category": False}

@router.get("/api/transactions/{transaction_id}/split")
def get_splits(
    transaction_id: str,
    user: dict = Depends(get_current_user)
):
    return get_splits_for_transaction(user["id"], transaction_id)
