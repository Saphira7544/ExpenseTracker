from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.api.routes import uploads


templates = Jinja2Templates(directory="app/templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    from app.core.config import settings
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(uploads.router)

@app.get("/")
async def root():
    return RedirectResponse(url="/upload")

@app.get("/upload")
async def upload_page(request: Request):
    return templates.TemplateResponse(request, "upload.html", {})