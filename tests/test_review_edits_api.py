import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.api.routes import uploads
from app.core.dependencies import get_current_user

USER = {"id": 7, "email": "me@example.com", "is_approved": True, "is_admin": False}


@pytest.fixture
def api(monkeypatch):
    calls = []
    monkeypatch.setattr(uploads, "commit_import",
                        lambda uid, iid, ids, edits: calls.append((ids, edits)) or {"files": [], "added": 1})
    main.app.dependency_overrides[get_current_user] = lambda: USER
    yield TestClient(main.app), calls
    main.app.dependency_overrides.clear()


def confirm(client, edits):
    return client.post("/api/uploads/x/confirm", json={"transaction_ids": ["T"], "edits": {"T": edits}})


def test_only_the_changed_fields_reach_the_import(api):
    client, calls = api
    r = confirm(client, {"description": "  Dinner ", "date": "2026-03-05", "amount": -12.345, "category": "Groceries"})
    assert r.status_code == 200
    assert calls == [(["T"], {"T": {"description": "Dinner", "date": "2026-03-05", "amount": -12.35, "category": "Groceries"}})]


def test_a_blank_category_means_uncategorized(api):
    client, calls = api
    assert confirm(client, {"category": ""}).status_code == 200
    assert calls[0][1] == {"T": {"category": None}}


@pytest.mark.parametrize("edit", [
    {"description": "   "},
    {"amount": 0},
    {"date": "05.03.2026"},
    {"category": "Not a category"},
    {"category": "Split"},
])
def test_bad_edits_are_refused_before_anything_is_imported(api, edit):
    client, calls = api
    assert confirm(client, edit).status_code == 422
    assert calls == []


def test_importing_without_edits_still_works(api):
    client, calls = api
    assert client.post("/api/uploads/x/confirm", json={"transaction_ids": ["T"]}).status_code == 200
    assert calls == [(["T"], {})]
