from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException

from legacy_db.db import create_db, create_splits_table, create_rules_table, create_users_and_ownership
from legacy_db.networth_db import create_networth_tables
from legacy_db.settings_db import create_settings_tables

from app.api.routes import uploads, transactions, rules, auth, networth, analytics, categories, settings as settings_routes
from app.core.config import settings
from app.core.dependencies import get_current_user

templates = Jinja2Templates(directory="app/templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    create_users_and_ownership()
    create_db()
    create_splits_table()
    create_rules_table()  
    create_networth_tables()
    create_settings_tables()
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth.router)
app.include_router(uploads.router)
app.include_router(transactions.router) 
app.include_router(rules.router)
app.include_router(networth.router)
app.include_router(analytics.router)
app.include_router(categories.router)
app.include_router(settings_routes.router)


@app.exception_handler(StarletteHTTPException)
async def redirect_unauthenticated_pages(request: Request, exc: StarletteHTTPException):
    # Pages send logged-out visitors to /login; API calls keep their JSON 401.
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return RedirectResponse(url="/login", status_code=302)
    return await http_exception_handler(request, exc)

@app.get("/")
async def dashboard(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(request, "dashboard.html", {"active_page": "dashboard", "user": user})


@app.get("/upload")
async def upload_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        request, "upload.html",
        {"active_page": "upload", "user": user}
    )

@app.get("/transactions")
async def transactions_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        request, "transactions.html",
        {"active_page": "transactions", "user": user}
    )

@app.get("/rules")
async def rules_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        request, "rules.html",
        {"active_page": "rules", "user": user}
    )

@app.get("/networth")
async def networth_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "networth.html",
        {"active_page": "networth", "user": user}
    )

@app.get("/networth/config")
async def networth_config_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "networth_config.html",
        {"active_page": "networth", "user": user}
    )

@app.get("/networth/analytics")
async def networth_analytics_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "networth_analytics.html",
        {"active_page": "networth_charts", "user": user}
    )

@app.get("/monthly")
async def monthly_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "monthly.html",
        {"active_page": "monthly", "user": user}
    )

@app.get("/settings")
async def settings_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"active_page": "settings", "user": user}
    )
