import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.core.categories import CATEGORIES
from app.core.dependencies import get_current_user
from app.services import categories

USER = {"id": 7, "email": "me@example.com", "is_approved": True, "is_admin": False}
PETS = {"id": 1, "name": "Pets", "color": "#0f766e", "sheet_group": "Leisure"}


@pytest.fixture
def with_pets(monkeypatch):
    monkeypatch.setattr(categories, "list_custom", lambda user_id: [PETS])


def test_own_categories_come_before_other(with_pets):
    names = categories.categories_for(7)
    assert names[-2:] == ["Pets", "Other"]
    assert set(names) == set(CATEGORIES) | {"Pets"}


def test_own_categories_get_their_colour_and_sheet_group(with_pets):
    assert categories.colors_for(7)["Pets"] == "#0f766e"
    groups = {g["name"]: g["categories"] for g in categories.sheet_groups_for(7)}
    assert "Pets" in groups["Leisure"]
    assert "Pets" not in groups["Other"]


def test_sheet_groups_are_not_changed_for_other_users(with_pets):
    categories.sheet_groups_for(7)
    from app.core.categories import SHEET_GROUPS
    assert all("Pets" not in g["categories"] for g in SHEET_GROUPS)


@pytest.mark.parametrize("name, ok", [
    ("Pets", False), ("pets", False), ("groceries", False), ("Split", False), ("Uncategorized", False),
    ("", False), ("x" * 41, False), ("Gifts", True),
])
def test_name_rules(with_pets, name, ok):
    assert (categories.name_problem(7, name) is None) == ok


def test_field_rules():
    assert categories.field_problem("#0f766e", "Food") is None
    assert categories.field_problem("red", "Food")
    assert categories.field_problem("#0f766e", "Not a group")


@pytest.fixture
def client(monkeypatch):
    main.app.dependency_overrides[get_current_user] = lambda: USER
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_new_category_is_accepted_everywhere_at_once(client, monkeypatch, with_pets):
    from app.api.routes import rules, transactions
    monkeypatch.setattr(rules, "add_rule", lambda category, keyword, uid: 3)
    monkeypatch.setattr(transactions, "update_transaction_category", lambda uid, tid, category: True)
    assert "Pets" in client.get("/api/categories").json()
    assert client.post("/api/rules", json={"category": "Pets", "keyword": "fressnapf"}).status_code == 200
    assert client.patch("/api/transactions/t1", json={"category": "Pets"}).status_code == 200
    assert client.patch("/api/transactions/t1", json={"category": "Nope"}).status_code == 422


def test_create_reports_problems(client, monkeypatch):
    added = []
    monkeypatch.setattr(categories, "add_category", lambda *a: added.append(a) or {})
    r = client.post("/api/categories", json={"name": "  Groceries ", "color": "#123456", "sheet_group": "Food"})
    assert r.status_code == 400 and "already" in r.json()["detail"]
    r = client.post("/api/categories", json={"name": "  Gym   Classes ", "color": "#ABCDEF", "sheet_group": "Leisure"})
    assert r.status_code == 200
    assert added == [(7, "Gym Classes", "#abcdef", "Leisure")]


def test_used_category_cannot_be_deleted(client, monkeypatch, with_pets):
    monkeypatch.setattr(categories, "usage",
                        lambda uid, names: {"Pets": {"transactions": 1, "rules": 2, "roles": 0}})
    r = client.delete("/api/categories/1")
    assert r.status_code == 409
    assert r.json()["detail"] == "Pets is still used by 1 transaction and 2 rules. Move those to another category first."
    assert client.delete("/api/categories/99").status_code == 404
