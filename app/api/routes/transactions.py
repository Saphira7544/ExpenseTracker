import re
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from app.core.categories import CATEGORIES
from app.core.dependencies import get_current_user
from app.services.transactions import (
    get_transactions, get_categories, get_accounts, update_transaction_category,
    get_transaction_by_id, save_splits, get_splits_for_transaction, undo_split,
    count_transactions, bulk_update_category, revert_to_auto, get_currencies,
    create_transaction, update_transaction, delete_transaction, split_edit_problem,
)
from app.services.settings import SUPPORTED_DISPLAY_CURRENCIES

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

class TransactionPayload(BaseModel):
    """All fields of the add/edit dialog. amount is signed: negative = money out."""
    date: date
    description: str
    amount: float
    currency: str
    account: str
    category: Optional[str] = None  # None = uncategorized

    @field_validator("description", "account")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("amount")
    @classmethod
    def _non_zero(cls, value: float) -> float:
        if abs(value) < 0.005:
            raise ValueError("must not be zero")
        return round(value, 2)

    @field_validator("currency")
    @classmethod
    def _currency_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("must be a 3-letter code such as CHF or EUR")
        return value

    @field_validator("category")
    @classmethod
    def _optional_category(cls, value: Optional[str]) -> Optional[str]:
        return None if value in (None, "") else _known_category(value)


@router.post("/api/transactions")
def add_transaction(payload: TransactionPayload, user: dict = Depends(get_current_user)):
    transaction_id = create_transaction(user["id"], payload.model_dump())
    return get_transaction_by_id(user["id"], transaction_id)


@router.put("/api/transactions/{transaction_id}")
def edit_transaction(transaction_id: str, payload: TransactionPayload, user: dict = Depends(get_current_user)):
    existing = get_transaction_by_id(user["id"], transaction_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Transaction not found")
    fields = payload.model_dump()
    problem = split_edit_problem(existing, fields)
    if problem:
        raise HTTPException(status_code=409, detail=problem)
    update_transaction(user["id"], existing, fields)
    return get_transaction_by_id(user["id"], transaction_id)


@router.delete("/api/transactions/{transaction_id}")
def remove_transaction(transaction_id: str, user: dict = Depends(get_current_user)):
    if not delete_transaction(user["id"], transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "deleted"}


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
        "accounts": get_accounts(user["id"]),
        # For the add/edit dialog: currencies already used plus the display ones.
        "currencies": sorted(set(get_currencies(user["id"])) | set(SUPPORTED_DISPLAY_CURRENCIES)),
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
