import os
import uuid
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.services.ingestion import stage_import, commit_import, discard_import

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


class ConfirmImport(BaseModel):
    # None = import every previewed row; otherwise only these (the ones left ticked).
    transaction_ids: Optional[list[str]] = None


@router.post("/api/uploads/preview")
async def preview_upload(
    files: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    """Parse and categorize the files without adding anything; returns what would be imported."""
    saved = [(file.filename, await _save_upload(file, user["id"])) for file in files]
    # Parsing, the DB and the LLM are all blocking; keep them off the event loop.
    return await run_in_threadpool(stage_import, user["id"], saved)


@router.post("/api/uploads/{import_id}/confirm")
def confirm_upload(import_id: str, payload: ConfirmImport, user: dict = Depends(get_current_user)):
    result = commit_import(user["id"], import_id, payload.transaction_ids)
    if result is None:
        raise HTTPException(status_code=404, detail="This upload preview has expired or was already imported. Upload the files again.")
    return result


@router.delete("/api/uploads/{import_id}")
def cancel_upload(import_id: str, user: dict = Depends(get_current_user)):
    discard_import(user["id"], import_id)
    return {"status": "discarded"}
