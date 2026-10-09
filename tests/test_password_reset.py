import logging
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.api.routes import auth as auth_routes
from app.core import auth as core_auth, dependencies
from app.core.config import settings
from app.services import email as email_service
from app.services import password_reset


@pytest.fixture
def client(monkeypatch):
    auth_routes.reset_limiter._failures.clear()
    auth_routes.reset_ip_limiter._failures.clear()
    return TestClient(main.app)


def test_tokens_are_stored_hashed_and_links_use_the_configured_address(monkeypatch):
    monkeypatch.setattr(settings, "APP_BASE_URL", "http://expenses.localhost")
    token = "abc-_123"
    assert password_reset.hash_token(token) != token
    assert len(password_reset.hash_token(token)) == 64
    assert password_reset.reset_link(token) == "http://expenses.localhost/reset-password?token=abc-_123"


def test_forgot_password_answers_the_same_for_unknown_emails(client, monkeypatch):
    asked = []
    monkeypatch.setattr(password_reset, "request_reset", lambda email: asked.append(email))
    known = client.post("/forgot-password", data={"email": "me@example.com"})
    unknown = client.post("/forgot-password", data={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.text == unknown.text and "If an account exists" in known.text
    assert asked == ["me@example.com", "nobody@example.com"]


def test_forgot_password_is_rate_limited_per_email(client, monkeypatch):
    monkeypatch.setattr(password_reset, "request_reset", lambda email: None)
    codes = [client.post("/forgot-password", data={"email": "me@example.com"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_reset_page_with_bad_token_says_expired(client, monkeypatch):
    monkeypatch.setattr(password_reset, "token_is_valid", lambda t: False)
    r = client.get("/reset-password?token=nope")
    assert r.status_code == 400 and "Link expired" in r.text


@pytest.mark.parametrize("password, confirm, message", [
    ("short", "short", "at least 8"),
    ("longenough1", "different1", "passwords don&#39;t match"),
])
def test_reset_rejects_bad_passwords(client, monkeypatch, password, confirm, message):
    called = []
    monkeypatch.setattr(password_reset, "reset_password", lambda t, p: called.append(p) or True)
    r = client.post("/reset-password", data={"token": "t", "password": password, "confirm": confirm})
    assert r.status_code == 400 and message in r.text and called == []


def test_successful_reset_redirects_to_login(client, monkeypatch):
    monkeypatch.setattr(password_reset, "reset_password", lambda t, p: (t, p) == ("tok", "new-password"))
    r = client.post("/reset-password", data={"token": "tok", "password": "new-password", "confirm": "new-password"},
                    follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login?reset=done"
    assert "changed" in client.get("/login?reset=done").text

    used = client.post("/reset-password", data={"token": "used", "password": "new-password", "confirm": "new-password"})
    assert used.status_code == 400 and "Link expired" in used.text


def test_reset_signs_out_older_sessions(monkeypatch):
    user = {"id": 1, "email": "me@example.com", "is_approved": True, "is_admin": False, "session_version": 1}
    monkeypatch.setattr(dependencies, "get_user_by_id", lambda uid: user)
    c = TestClient(main.app)
    c.cookies.set(settings.SESSION_COOKIE_NAME, core_auth.create_session_token(1, 0))  # from before the reset
    assert c.get("/api/transactions/filters").status_code == 401
    c.cookies.set(settings.SESSION_COOKIE_NAME, core_auth.create_session_token(1, 1))
    assert c.get("/api/categories").status_code == 200


def test_old_cookies_without_a_version_still_work_until_a_reset():
    token = core_auth.serializer.dumps({"user_id": 5})   # cookie format before this change
    assert core_auth.read_session_token(token) == {"user_id": 5, "v": 0}


@pytest.mark.parametrize("port, cls", [(587, "SMTP"), (465, "SMTP_SSL")])
def test_send_email_uses_tls(monkeypatch, port, cls):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", port)
    monkeypatch.setattr(settings, "SMTP_USER", "me@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-password")
    monkeypatch.setattr(settings, "SMTP_FROM", "me@example.com")
    with mock.patch(f"smtplib.{cls}") as smtp_cls:
        email_service.send_email("me@example.com", "Subject", "Body", "<p>Body</p>")
    smtp = smtp_cls.return_value.__enter__.return_value
    if port == 587:
        names = [c[0] for c in smtp.method_calls]
        assert names.index("starttls") < names.index("login")   # never send the password unencrypted
    smtp.login.assert_called_once_with("me@example.com", "app-password")
    sent = smtp.send_message.call_args[0][0]
    assert sent["To"] == "me@example.com" and sent["Subject"] == "Subject"


def test_without_smtp_the_link_goes_to_the_server_log(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(password_reset, "create_reset_token", lambda uid: "the-token")
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        password_reset._deliver("me@example.com", 1)
    assert "reset-password?token=the-token" in caplog.text
