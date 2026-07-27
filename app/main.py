from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from legacy_db.db import create_db, create_splits_table, create_rules_table, create_users_and_ownership
from legacy_db.networth_db import create_networth_tables

from app.api.routes import uploads, transactions, rules, auth, networth
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
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth.router)
app.include_router(uploads.router)
app.include_router(transactions.router)
app.include_router(rules.router)
app.include_router(networth.router)

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