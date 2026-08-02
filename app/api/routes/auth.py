from fastapi import APIRouter, Form, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.config import settings
from app.core.auth import create_session_token
from app.core.dependencies import require_admin 
from app.services.users import create_user, authenticate_user, get_user_by_email
from sqlalchemy import text
from app.db.session import engine


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})

@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    user = authenticate_user(email, password)
    if not user:
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid email or password"}, status_code=400)

    if not user["is_approved"]:
        return templates.TemplateResponse(request, "login.html", {"error": "Your account is pending approval"}, status_code=403)

    token = create_session_token(user["id"])
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(key=settings.SESSION_COOKIE_NAME, value=token, httponly=True, samesite="lax")
    return response

@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"error": None})

@router.post("/register")
async def register(request: Request, email: str = Form(...), password: str = Form(...)):
    existing = get_user_by_email(email)
    if existing:
        return templates.TemplateResponse(request, "register.html", {"error": "Email already exists"}, status_code=400)

    create_user(email, password)  # is_approved defaults to False
    return templates.TemplateResponse(
        request, "register.html",
        {"error": None, "message": "Account requested. You'll be notified once approved."}
    )

@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return response

@router.get("/admin/pending-users")
async def pending_users(admin: dict = Depends(require_admin)):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, email, created_at FROM users WHERE is_approved = FALSE")).mappings().all()
    return [dict(r) for r in rows]

@router.post("/admin/approve-user/{user_id}")
async def approve_user(user_id: int, admin: dict = Depends(require_admin)):
    with engine.connect() as conn:
        conn.execute(text("UPDATE users SET is_approved = TRUE WHERE id = :id"), {"id": user_id})
        conn.commit()
    return {"status": "approved", "user_id": user_id}