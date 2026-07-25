from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.api.routes import uploads
from app.core.config import settings

templates = Jinja2Templates(directory="app/templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(uploads.router)

@app.get("/")
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"active_page": "dashboard"})

@app.get("/upload")
async def upload_page(request: Request):
    return templates.TemplateResponse(
        request, "upload.html",
        {"active_page": "upload", "api_key": settings.ADMIN_API_KEY}
    )