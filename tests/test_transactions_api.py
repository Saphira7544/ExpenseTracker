import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.api.routes import transactions as routes
from app.core.dependencies import get_current_user
from app.services.transactions import split_edit_problem

USER = {"id": 7, "email": "me@example.com", "is_approved": True, "is_admin": False}

VALID = {
    "date": "2026-03-05",
    "description": "  Dinner  ",
    "amount": -42.5,
    "currency": "chf",
    "account": "Cash",
    "category": "Restaurants/Bars",
}


@pytest.fixture
def api(monkeypatch):
    """Client with auth and the DB-backed service functions stubbed out."""
    store = {
        "imported-1": {"transactionid": "imported-1", "amount": -100.0, "category": "Groceries"},
        "split-1": {"transactionid": "split-1", "amount": -100.0, "category": "Split"},
    }
    calls = {}

    monkeypatch.setattr(routes, "get_transaction_by_id", lambda uid, tid: store.get(tid))
    monkeypatch.setattr(routes, "create_transaction",
                        lambda uid, fields: calls.setdefault("create", (uid, fields)) and "manual-abc")
    monkeypatch.setattr(routes, "update_transaction",
                        lambda uid, existing, fields: calls.setdefault("update", (uid, existing, fields)))
    monkeypatch.setattr(routes, "delete_transaction", lambda uid, tid: store.pop(tid, None) is not None)

    main.app.dependency_overrides[get_current_user] = lambda: USER
    yield TestClient(main.app), calls
    main.app.dependency_overrides.clear()


def test_create_normalises_fields(api):
    client, calls = api
    r = client.post("/api/transactions", json=VALID)
    assert r.status_code == 200
    uid, fields = calls["create"]
    assert uid == 7
    assert fields["description"] == "Dinner"
    assert fields["currency"] == "CHF"
    assert fields["amount"] == -42.5
    assert str(fields["date"]) == "2026-03-05"


@pytest.mark.parametrize("change", [
    {"amount": 0},
    {"currency": "francs"},
    {"description": "   "},
    {"account": ""},
    {"category": "Split"},          # only the split endpoint may set Split
    {"category": "Not a category"},
    {"date": "05.03.2026"},
])
def test_create_rejects_invalid_fields(api, change):
    client, calls = api
    r = client.post("/api/transactions", json={**VALID, **change})
    assert r.status_code == 422
    assert "create" not in calls


def test_empty_category_means_uncategorized(api):
    client, calls = api
    client.post("/api/transactions", json={**VALID, "category": ""})
    assert calls["create"][1]["category"] is None


def test_imported_transactions_can_be_edited(api):
    client, calls = api
    r = client.put("/api/transactions/imported-1", json={**VALID, "amount": -120})
    assert r.status_code == 200
    assert calls["update"][2]["amount"] == -120


def test_split_transaction_amount_is_locked(api):
    client, calls = api
    r = client.put("/api/transactions/split-1", json={**VALID, "amount": -80, "category": None})
    assert r.status_code == 409
    assert "update" not in calls

    r = client.put("/api/transactions/split-1", json={**VALID, "amount": -100, "category": None})
    assert r.status_code == 200  # other fields can still change


def test_edit_and_delete_unknown_transaction(api):
    client, _ = api
    assert client.put("/api/transactions/nope", json=VALID).status_code == 404
    assert client.delete("/api/transactions/nope").status_code == 404
    assert client.delete("/api/transactions/imported-1").status_code == 200


def test_split_edit_problem():
    split = {"category": "Split", "amount": -100.0}
    assert split_edit_problem(split, {"amount": -100.0}) is None
    assert split_edit_problem(split, {"amount": 100.0}) is not None   # sign flip
    assert split_edit_problem({"category": "Groceries", "amount": -100.0}, {"amount": 5.0}) is None
