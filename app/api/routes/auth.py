from fastapi import APIRouter, Form, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from app.core.templates import templates
from app.core.config import settings
from app.core.auth import create_session_token, password_problem
from app.core.dependencies import require_admin
from app.core.rate_limit import FailureLimiter
from app.services.users import (
    create_user, authenticate_user, get_user_by_email, list_pending_users, set_user_approved,
)


router = APIRouter()


# 10 failed logins per email (or per client IP) within 15 minutes locks that key out.
login_limiter = FailureLimiter(max_failures=10, window_seconds=15 * 60)

REGISTERED_MESSAGE = "Account requested. You'll be notified once approved."

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})

@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    keys = [f"email:{email.lower().strip()}", f"ip:{request.client.host if request.client else 'unknown'}"]
    if any(login_limiter.is_blocked(k) for k in keys):
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Too many failed attempts. Try again in a few minutes."},
            status_code=429,
        )

    user = authenticate_user(email, password)
    if not user:
        for k in keys:
            login_limiter.record_failure(k)
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid email or password"}, status_code=400)

    for k in keys:
        login_limiter.reset(k)

    if not user["is_approved"]:
        return templates.TemplateResponse(request, "login.html", {"error": "Your account is pending approval"}, status_code=403)

    token = create_session_token(user["id"])
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    return response

@router.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"error": None})

@router.post("/register")
def register(request: Request, email: str = Form(...), password: str = Form(...)):
    problem = password_problem(password)
    if problem:
        return templates.TemplateResponse(request, "register.html", {"error": problem}, status_code=400)

    # Same response whether or not the email already exists, so the form
    # can't be used to discover who has an account.
    if not get_user_by_email(email):
        create_user(email, password)  # is_approved defaults to False
    return templates.TemplateResponse(
        request, "register.html",
        {"error": None, "message": REGISTERED_MESSAGE}
    )

@router.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return response

@router.get("/admin/pending-users")
def pending_users(admin: dict = Depends(require_admin)):
    return list_pending_users()

@router.post("/admin/users/{user_id}/approve")
def approve_user(user_id: int, admin: dict = Depends(require_admin)):
    if not set_user_approved(user_id, True):
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user_id, "is_approved": True}
