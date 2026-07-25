from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from legacy_db.db import create_db, create_splits_table
from app.api.routes import uploads, transactions
from app.core.config import settings

templates = Jinja2Templates(directory="app/templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    create_db()
    create_splits_table()
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(uploads.router)
app.include_router(transactions.router)

@app.get("/")
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"active_page": "dashboard"})

@app.get("/upload")
async def upload_page(request: Request):
    return templates.TemplateResponse(
        request, "upload.html",
        {"active_page": "upload", "api_key": settings.ADMIN_API_KEY}
    )

@app.get("/transactions")
async def transactions_page(request: Request):
    return templates.TemplateResponse(request, "transactions.html", {"active_page": "transactions", "api_key": settings.ADMIN_API_KEY})