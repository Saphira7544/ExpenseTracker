import os
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.services.ingestion import process_uploaded_file

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def _safe_filename(raw: str | None) -> str:
    # Browsers send a bare name, but nothing stops a client sending "..\..\x".
    name = os.path.basename((raw or "").replace("\\", "/")).strip().strip(".")
    return name or "upload.csv"


async def _save_upload(file: UploadFile, user_id: int) -> str:
    # Each upload gets its own directory so same-named files never overwrite
    # each other (across users or uploads); the parser records the basename
    # as sourceFile, so the original name is preserved inside it.
    directory = os.path.join(settings.UPLOAD_DIR, str(user_id), uuid.uuid4().hex)
    os.makedirs(directory, exist_ok=True)
    save_path = os.path.join(directory, _safe_filename(file.filename))

    size = 0
    with open(save_path, "wb") as f:
        while chunk := await file.read(CHUNK_SIZE):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                f.close()
                os.remove(save_path)
                raise HTTPException(
                    status_code=413,
                    detail=f"{file.filename} exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                )
            f.write(chunk)
    return save_path


@router.post("/api/uploads")
async def upload_files(
    files: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    results = []

    for file in files:
        save_path = await _save_upload(file, user["id"])
        # Parsing, the DB and the LLM are all blocking; keep them off the event loop.
        try:
            summary = await run_in_threadpool(process_uploaded_file, save_path, user_id=user["id"])
        except ValueError as exc:
            if "Could not detect file format" not in str(exc):
                raise
            raise HTTPException(
                status_code=400,
                detail=f"{file.filename}: no bank format recognises this file. "
                       f"Add or fix one on the Banks page.",
            )
        results.append({"filename": file.filename, **summary})

    return {"uploaded": results}
