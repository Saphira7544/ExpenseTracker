from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.dependencies import get_current_user
from app.services.networth import (
    get_networth_dashboard,
    get_lookup_bundle,
    list_lookup,
    create_lookup,
    update_lookup,
    delete_lookup,
    create_account,
    update_account,
    delete_account,
    create_valuation,
    update_valuation,
    delete_valuation,
    create_snapshot,
    update_snapshot,
    delete_snapshot,
    compute_snapshot_from_valuations,
)

router = APIRouter()

class LookupCreate(BaseModel):
    value: str
    sort_order: int = 0

class LookupUpdate(BaseModel):
    value: str
    sort_order: int = 0
    is_active: bool = True

class AccountPayload(BaseModel):
    account_name: str
    institution_id: Optional[int] = None
    asset_category_id: Optional[int] = None
    account_type_id: Optional[int] = None
    currency_id: Optional[int] = None
    liquidity_status_id: Optional[int] = None
    ticker_symbol: Optional[str] = None
    is_active: bool = True

class ValuationPayload(BaseModel):
    account_id: int
    valuation_date: str
    quantity: Optional[float] = None
    avg_purchase_price: Optional[float] = None
    current_price: Optional[float] = None
    current_value_original: Optional[float] = None
    exchange_rate_to_chf: Optional[float] = None
    current_value_chf: float
    source: Optional[str] = "manual"
    note: Optional[str] = None

class SnapshotPayload(BaseModel):
    snapshot_date: str
    total_liquid_chf: float
    total_illiquid_chf: float
    total_networth_chf: float
    mom_change_chf: Optional[float] = None
    mom_change_pct: Optional[float] = None
    notes: Optional[str] = None

@router.get("/api/networth/dashboard")
async def networth_dashboard(user: dict = Depends(get_current_user)):
    return get_networth_dashboard(user["id"])

@router.get("/api/networth/lookups")
async def networth_lookups(user: dict = Depends(get_current_user)):
    return get_lookup_bundle(user["id"])

@router.get("/api/networth/lookups/{table_key}")
async def get_lookup_items(table_key: str, user: dict = Depends(get_current_user)):
    return list_lookup(table_key, user["id"])

@router.post("/api/networth/lookups/{table_key}")
async def create_lookup_item(table_key: str, payload: LookupCreate, user: dict = Depends(get_current_user)):
    item_id = create_lookup(table_key, user["id"], payload.value, payload.sort_order)
    return {"id": item_id}

@router.patch("/api/networth/lookups/{table_key}/{item_id}")
async def update_lookup_item(table_key: str, item_id: int, payload: LookupUpdate, user: dict = Depends(get_current_user)):
    ok = update_lookup(table_key, user["id"], item_id, payload.value, payload.sort_order, payload.is_active)
    if not ok:
        raise HTTPException(status_code=404, detail="Lookup item not found")
    return {"status": "ok"}

@router.delete("/api/networth/lookups/{table_key}/{item_id}")
async def delete_lookup_item(table_key: str, item_id: int, user: dict = Depends(get_current_user)):
    ok = delete_lookup(table_key, user["id"], item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Lookup item not found")
    return {"status": "deleted"}

@router.post("/api/networth/accounts")
async def add_account(payload: AccountPayload, user: dict = Depends(get_current_user)):
    account_id = create_account(user["id"], payload.dict())
    return {"id": account_id}

@router.patch("/api/networth/accounts/{account_id}")
async def edit_account(account_id: int, payload: AccountPayload, user: dict = Depends(get_current_user)):
    ok = update_account(user["id"], account_id, payload.dict())
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "ok"}

@router.delete("/api/networth/accounts/{account_id}")
async def remove_account(account_id: int, user: dict = Depends(get_current_user)):
    ok = delete_account(user["id"], account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "deleted"}

@router.post("/api/networth/valuations")
async def add_valuation(payload: ValuationPayload, user: dict = Depends(get_current_user)):
    valuation_id = create_valuation(user["id"], payload.dict())
    return {"id": valuation_id}

@router.patch("/api/networth/valuations/{valuation_id}")
async def edit_valuation(valuation_id: int, payload: ValuationPayload, user: dict = Depends(get_current_user)):
    ok = update_valuation(user["id"], valuation_id, payload.dict())
    if not ok:
        raise HTTPException(status_code=404, detail="Valuation not found")
    return {"status": "ok"}

@router.delete("/api/networth/valuations/{valuation_id}")
async def remove_valuation(valuation_id: int, user: dict = Depends(get_current_user)):
    ok = delete_valuation(user["id"], valuation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Valuation not found")
    return {"status": "deleted"}

@router.post("/api/networth/snapshots")
async def add_snapshot(payload: SnapshotPayload, user: dict = Depends(get_current_user)):
    snapshot_id = create_snapshot(user["id"], payload.dict())
    return {"id": snapshot_id}

@router.patch("/api/networth/snapshots/{snapshot_id}")
async def edit_snapshot(snapshot_id: int, payload: SnapshotPayload, user: dict = Depends(get_current_user)):
    ok = update_snapshot(user["id"], snapshot_id, payload.dict())
    if not ok:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"status": "ok"}

@router.delete("/api/networth/snapshots/{snapshot_id}")
async def remove_snapshot(snapshot_id: int, user: dict = Depends(get_current_user)):
    ok = delete_snapshot(user["id"], snapshot_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"status": "deleted"}

@router.post("/api/networth/compute-snapshot")
async def compute_snapshot_endpoint(user: dict = Depends(get_current_user)):
    """
    Compute totals by summing current valuations for user:
     - totals by liquidity: Liquid vs Illiquid
    """
    totals = compute_snapshot_from_valuations(user["id"])
    return totals