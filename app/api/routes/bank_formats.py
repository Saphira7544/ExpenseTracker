import codecs
import json
import os
import re
import tempfile
from typing import Literal, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError, field_validator, model_validator

from app.core.dependencies import get_current_user
from app.services.bank_formats import (
    DuplicateFormat, create_format, delete_format, detection_configs, list_formats, normalize_config,
    update_format,
)
from parsers.detector import _matches_header, detect_config
from parsers.generic_parser import GenericParser
from utils.file_utils import read_file_lines

router = APIRouter()

SEPARATORS = [";", ",", "\t", "|"]
ENCODINGS = ["latin1", "utf-8", "utf-8-sig", "cp1252", "utf-16"]
MAX_PREVIEW_BYTES = 10 * 1024 * 1024
PREVIEW_ROWS = 15


class BankFormatPayload(BaseModel):
    """One bank file format, as edited in the Banks dialog."""
    bank: str
    file_type: str
    account: str
    header: list[str]
    sep: str = ";"
    encoding: str = "latin1"
    date_col: str
    date_format: str
    desc_cols: list[str]
    amount_mode: Literal["debit_credit", "single"] = "debit_credit"
    debit_col: Optional[str] = None
    credit_col: Optional[str] = None
    amount_col: Optional[str] = None
    invert_amount: bool = False
    currency_col: Optional[str] = None
    fixed_currency: Optional[str] = None
    id_col: Optional[str] = None
    decimal_sep: Literal[".", ","] = "."
    drop_empty_amount: bool = True
    is_active: bool = True

    @field_validator("bank")
    @classmethod
    def _bank_key(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9 _-]{0,39}", value):
            raise ValueError("use letters, numbers, spaces, - or _ (e.g. 'ubs', 'revolut')")
        return value

    @field_validator("file_type", "account", "date_col")
    @classmethod
    def _required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("header", "desc_cols")
    @classmethod
    def _non_empty_list(cls, value: list[str]) -> list[str]:
        value = [v.strip() for v in value if v and v.strip()]
        if not value:
            raise ValueError("add at least one")
        return value

    @field_validator("sep")
    @classmethod
    def _separator(cls, value: str) -> str:
        if value not in SEPARATORS:
            raise ValueError("choose ; , tab or |")
        return value

    @field_validator("encoding")
    @classmethod
    def _encoding(cls, value: str) -> str:
        try:
            codecs.lookup(value)
        except LookupError:
            raise ValueError(f"unknown encoding '{value}'")
        return value

    @field_validator("date_format")
    @classmethod
    def _date_format(cls, value: str) -> str:
        if "%" not in value:
            raise ValueError("use codes like %d.%m.%Y")
        return value.strip()

    @field_validator("fixed_currency")
    @classmethod
    def _currency(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("must be a 3-letter code such as CHF")
        return value

    @model_validator(mode="after")
    def _modes(self):
        blank = lambda v: not (v and v.strip())
        if self.amount_mode == "debit_credit":
            if blank(self.debit_col) or blank(self.credit_col):
                raise ValueError("debit and credit columns are required")
            self.amount_col, self.invert_amount = None, False
        else:
            if blank(self.amount_col):
                raise ValueError("amount column is required")
            self.debit_col = self.credit_col = None
        if blank(self.currency_col) and not self.fixed_currency:
            raise ValueError("choose a currency column or a fixed currency")
        return self

    def to_config(self) -> dict:
        return normalize_config(self.model_dump(exclude={"amount_mode", "is_active"}))


def _with_mode(fmt: dict) -> dict:
    fmt["config"]["amount_mode"] = "single" if fmt["config"].get("amount_col") else "debit_credit"
    return fmt


@router.get("/api/bank-formats")
def get_formats(user: dict = Depends(get_current_user)):
    return {
        "formats": [_with_mode(f) for f in list_formats(user["id"])],
        "separators": SEPARATORS,
        "encodings": ENCODINGS,
    }


@router.post("/api/bank-formats")
def add_format(payload: BankFormatPayload, user: dict = Depends(get_current_user)):
    try:
        return {"id": create_format(user["id"], payload.to_config(), payload.is_active)}
    except DuplicateFormat as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.put("/api/bank-formats/{format_id}")
def edit_format(format_id: int, payload: BankFormatPayload, user: dict = Depends(get_current_user)):
    try:
        ok = update_format(user["id"], format_id, payload.to_config(), payload.is_active)
    except DuplicateFormat as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="Format not found")
    return {"status": "ok"}


@router.delete("/api/bank-formats/{format_id}")
def remove_format(format_id: int, user: dict = Depends(get_current_user)):
    if not delete_format(user["id"], format_id):
        raise HTTPException(status_code=404, detail="Format not found")
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# "Test with a file": show what a (possibly unsaved) format makes of a file
# ---------------------------------------------------------------------------

def _validation_message(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"]) or "format"
        parts.append(f"{field}: {err['msg'].removeprefix('Value error, ')}")
    return "; ".join(parts)


def suggest_file_settings(path: str) -> dict:
    """Best guess at encoding and separator, offered when setting up a new bank."""
    with open(path, "rb") as f:
        raw = f.read(64 * 1024)
    if raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    else:
        try:
            raw.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            encoding = "latin1"
    text_head = raw.decode(encoding if encoding != "utf-8-sig" else "utf-8", errors="replace")
    # The separator that splits the most lines consistently, judged on the longest of the first lines.
    first_lines = [l for l in text_head.splitlines()[:20] if l.strip()]
    widest = max(first_lines, key=len, default="")
    sep = max(SEPARATORS, key=lambda s: widest.count(s))
    return {"encoding": encoding, "sep": sep if widest.count(sep) else ";"}


def preview_file(path: str, raw_config: dict, saved_configs: list[dict]) -> dict:
    """Columns and first rows of the file, plus the parse result if the config is complete."""
    sep = raw_config.get("sep") or ";"
    encoding = raw_config.get("encoding") or "latin1"
    signatures = [s for s in raw_config.get("header") or [] if s and s.strip()]
    result = {"header_found": False, "columns": [], "raw_rows": [], "transactions": [],
              "total": 0, "error": None, "detected": None, "suggested": suggest_file_settings(path)}

    try:
        lines = read_file_lines(path, encoding)
    except LookupError:
        result["error"] = f"Unknown encoding '{encoding}'"
        return result

    # Which saved format (if any) would pick this file up on upload?
    try:
        detected = detect_config(path, saved_configs)
        result["detected"] = f"{detected['bank'].upper()} · {detected['file_type']}"
    except ValueError:
        pass

    # Find the header row: the first line containing a signature, else the first line.
    skiprows = 0
    if signatures:
        result["header_found"] = _matches_header(signatures, lines)
        skiprows = next((i for i, line in enumerate(lines) if any(s.strip() in line for s in signatures)), 0)

    try:
        sample = pd.read_csv(path, sep=sep, skiprows=skiprows, encoding=encoding, dtype=str, nrows=5,
                             engine="python", on_bad_lines="skip")
        sample.columns = [str(c).strip() for c in sample.columns]
        result["columns"] = [c for c in sample.columns if not c.startswith("Unnamed:")]
        result["raw_rows"] = sample.fillna("").values.tolist()
    except Exception as exc:
        result["error"] = f"Could not read the file as CSV: {exc}"
        return result

    try:
        payload = BankFormatPayload(**raw_config)
    except ValidationError as exc:
        result["error"] = "Fill in the format to see parsed transactions (" + _validation_message(exc) + ")"
        return result

    try:
        transactions = GenericParser(payload.to_config()).parse(path)
    except KeyError as exc:
        result["error"] = f"Column {exc} isn't in the file. Columns found: {', '.join(result['columns'])}"
        return result
    except Exception as exc:
        result["error"] = f"Parsing failed: {exc}"
        return result

    result["total"] = len(transactions)
    result["transactions"] = [
        {"date": t.date.date().isoformat(), "description": t.description, "amount": t.amount,
         "currency": t.currency, "id": t.transactionId}
        for t in transactions[:PREVIEW_ROWS]
    ]
    if not transactions:
        result["error"] = "No transactions found: check the date column/format and amount columns."
    return result


@router.post("/api/bank-formats/preview")
async def preview(
    file: UploadFile = File(...),
    config: str = Form("{}"),
    user: dict = Depends(get_current_user),
):
    try:
        raw_config = json.loads(config)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid format data")

    content = await file.read(MAX_PREVIEW_BYTES + 1)
    if len(content) > MAX_PREVIEW_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB")

    # Parsed from a temp file and deleted right away: previews never import anything.
    fd, path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        saved = await run_in_threadpool(detection_configs, user["id"])
        return await run_in_threadpool(preview_file, path, raw_config, saved)
    finally:
        os.remove(path)
