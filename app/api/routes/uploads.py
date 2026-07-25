import os
from fastapi import APIRouter, UploadFile, File, Depends
from app.core.config import settings
from app.core.security import verify_api_key
from app.services.ingestion import process_uploaded_file

router = APIRouter()

@router.post("/api/uploads")
async def upload_files(
    files: list[UploadFile] = File(...),
    api_key: str = Depends(verify_api_key),
):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    results = []

    for file in files:
        save_path = os.path.join(settings.UPLOAD_DIR, file.filename)
        with open(save_path, "wb") as f:
            f.write(await file.read())

        summary = process_uploaded_file(save_path)
        results.append({"filename": file.filename, **summary})

    return {"uploaded": results}