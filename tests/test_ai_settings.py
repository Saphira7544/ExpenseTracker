from unittest import mock

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.api.routes import settings as routes
from app.core import crypto
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.services import ai_settings
from categorizers import openAI as categorizer

USER = {"id": 7, "email": "me@example.com", "is_approved": True, "is_admin": False}
KEY = "sk-test-" + "a" * 40
REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def status_error(cls, status, body):
    return cls("error mentioning sk-tes***aaaa", response=httpx.Response(status, request=REQUEST), body=body)


NO_CREDITS = status_error(openai.RateLimitError, 429, {"type": "insufficient_quota", "code": "insufficient_quota"})
BAD_KEY = status_error(openai.AuthenticationError, 401, {"type": "invalid_request_error", "code": "invalid_api_key"})


def test_keys_are_encrypted_and_unreadable_with_another_secret(monkeypatch):
    token = crypto.encrypt(KEY)
    assert KEY not in token and crypto.decrypt(token) == KEY
    monkeypatch.setattr(settings, "APP_SECRET_KEY", "another-secret-" + "y" * 32)
    assert crypto.decrypt(token) is None


def test_saved_key_wins_over_env_and_env_is_the_fallback(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "env-key")
    monkeypatch.setattr(ai_settings, "_load", lambda uid: {"encrypted_key": crypto.encrypt(KEY), "updated_at": mock.Mock()})
    assert ai_settings.get_api_key(7) == KEY
    monkeypatch.setattr(ai_settings, "_load", lambda uid: None)
    assert ai_settings.get_api_key(7) == "env-key"
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    assert ai_settings.get_api_key(7) is None


@pytest.mark.parametrize("exc, expected", [
    (NO_CREDITS, "no credits left"),
    (status_error(openai.RateLimitError, 429, {"type": "tokens", "code": "rate_limit_exceeded"}), "limiting requests"),
    (BAD_KEY, "rejected the API key"),
    (openai.APIConnectionError(request=REQUEST), "Couldn't reach OpenAI"),
    (status_error(openai.InternalServerError, 500, {}), "status 500"),
    (ValueError("boom"), "logs/server.log"),
])
def test_errors_are_explained_without_quoting_openai(exc, expected):
    message = categorizer.error_message(exc)
    assert expected in message and "sk-" not in message


def classify_with(monkeypatch, side_effect, n=50):
    create = mock.Mock(side_effect=side_effect)
    client = mock.Mock()
    client.chat.completions.create = create
    monkeypatch.setattr(categorizer, "OpenAI", lambda api_key: client)
    return (*categorizer.classify_transactions_batch(["x"] * n, ["Other"], KEY, batch_size=20), create)


def test_no_key_reports_it_without_calling_openai():
    assert categorizer.classify_transactions_batch(["a", "b"], ["Other"], None) == ([None, None], categorizer.NO_KEY_MESSAGE)


def test_running_out_of_credit_stops_after_the_first_batch(monkeypatch):
    results, problem, create = classify_with(monkeypatch, NO_CREDITS)
    assert results == [None] * 50 and "no credits" in problem
    assert create.call_count == 1


def test_a_temporary_failure_keeps_the_other_batches(monkeypatch):
    answer = mock.MagicMock()
    answer.choices[0].message.content = '{"results": [{"index": 1, "category": "Other"}]}'
    results, problem, create = classify_with(monkeypatch, [openai.APIConnectionError(request=REQUEST), answer, answer])
    assert create.call_count == 3 and len(results) == 50
    assert results[0] is None and results[20] == "Other" and results[40] == "Other"
    assert "Couldn't reach" in problem


@pytest.fixture
def client():
    main.app.dependency_overrides[get_current_user] = lambda: USER
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture
def saved(monkeypatch):
    stored = []
    monkeypatch.setattr(routes, "save_api_key", lambda uid, key: stored.append(key))
    monkeypatch.setattr(routes, "key_status", lambda uid: {"source": "saved", "saved_at": "2026-11-04", "unreadable": False})
    return stored


def test_a_working_key_is_saved_and_never_returned(client, saved, monkeypatch):
    monkeypatch.setattr(routes, "check_key", lambda key: (True, None))
    r = client.put("/api/settings/ai-key", json={"api_key": f"  {KEY}\n"})
    assert r.status_code == 200 and saved == [KEY] and KEY not in r.text


def test_a_rejected_key_is_not_saved(client, saved, monkeypatch):
    monkeypatch.setattr(routes, "check_key", lambda key: (False, "OpenAI rejected the API key."))
    r = client.put("/api/settings/ai-key", json={"api_key": KEY})
    assert r.status_code == 400 and saved == [] and KEY not in r.text


def test_a_key_without_credit_is_saved_with_a_warning(client, saved, monkeypatch):
    monkeypatch.setattr(routes, "check_key", lambda key: (True, "no credits"))
    r = client.put("/api/settings/ai-key", json={"api_key": KEY})
    assert saved == [KEY] and r.json()["warning"] == "no credits"


@pytest.mark.parametrize("bad", ["", "short", "has spaces " + "a" * 30, "chaves-com-acentuação-" + "a" * 30])
def test_things_that_are_not_keys_are_refused_without_echoing_them(client, saved, bad):
    r = client.put("/api/settings/ai-key", json={"api_key": bad})
    assert r.status_code == 400 and saved == []
    assert not bad or bad not in r.text


def test_status_never_contains_the_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "env-key")
    row = {"encrypted_key": crypto.encrypt(KEY), "updated_at": mock.Mock(isoformat=lambda: "2026-11-04")}
    monkeypatch.setattr(ai_settings, "_load", lambda uid: row)
    assert ai_settings.key_status(7) == {"source": "saved", "saved_at": "2026-11-04", "unreadable": False}
    row["encrypted_key"] = "not-readable"
    assert ai_settings.key_status(7) == {"source": "env", "saved_at": None, "unreadable": True}
