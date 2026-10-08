"""Importing bank files in two steps:

1. stage_import(): parse each file, drop excluded rows and rows that were
   already imported, categorize what's left (rules, then the LLM) and keep it
   in staged_imports. Nothing is added to the transactions yet.
2. commit_import(): insert the staged rows the user kept, exactly as previewed.
   discard_import() throws a staged upload away.
"""
import json
import uuid
from datetime import datetime

from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine
from app.services.bank_formats import detection_configs
from app.services.settings import get_exclusion_patterns
from categorizers.openAI import classify_transactions_batch
from categorizers.rule_categorizer import rule_based_categorize
from legacy_db.db import insert_transactions
from models.transaction import Transaction, TransactionType
from parsers.detector import detect_config
from parsers.generic_parser import GenericParser

STAGED_IMPORT_TTL_HOURS = 24


class UnknownFormat(ValueError):
    pass


def parse_transactions(file_path: str, user_id: int):
    """Returns (transactions, rows skipped by the user's exclusions, format config)."""
    try:
        config = detect_config(file_path, detection_configs(user_id))
    except ValueError:
        raise UnknownFormat("No bank format recognises this file. Add or fix one on the Banks page.")
    bank_parser = GenericParser(config, get_exclusion_patterns(user_id, config["bank"]))
    transactions = bank_parser.parse(file_path)
    return transactions, bank_parser.excluded_count, config


def categorize_transactions(transactions, user_id: int, run_llm: bool = True) -> dict[str, str]:
    """Fill in categories; returns {transactionId: "rule" | "llm"} for the ones categorized."""
    rule_based_categorize(transactions, user_id)
    source = {t.transactionId: "rule" for t in transactions if t.category}
    uncategorized = [t for t in transactions if not t.category]

    if run_llm and uncategorized:
        categories = classify_transactions_batch([t.description for t in uncategorized])
        for t, cat in zip(uncategorized, categories):
            if cat:
                t.category = cat
                source[t.transactionId] = "llm"
    return source


def existing_ids(user_id: int, transaction_ids: list[str]) -> set[str]:
    if not transaction_ids:
        return set()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT transactionId FROM transactions WHERE user_id = :user_id AND transactionId = ANY(:ids)"),
            {"user_id": user_id, "ids": transaction_ids}
        ).all()
    return {r[0] for r in rows}


def split_new(transactions, already_imported: set[str], seen_in_upload: set[str]):
    """Separate rows that would be added from rows already in the database or
    already appearing earlier in this upload (e.g. two overlapping exports).
    Updates seen_in_upload. Returns (new, already_imported_count, duplicate_in_upload_count)."""
    new, existing, repeated = [], 0, 0
    for t in transactions:
        if t.transactionId in already_imported:
            existing += 1
        elif t.transactionId in seen_in_upload:
            repeated += 1
        else:
            seen_in_upload.add(t.transactionId)
            new.append(t)
    return new, existing, repeated


def _serialize(t: Transaction, file_index: int, category_source: str | None) -> dict:
    return {
        "id": t.transactionId,
        "file": file_index,
        "date": t.date.date().isoformat(),
        "type": t.transactionType.value,
        "description": t.description,
        "amount": t.amount,
        "currency": t.currency,
        "account": t.account,
        "source_file": t.sourceFile,
        "category": t.category,
        "category_source": category_source,
    }


def _deserialize(row: dict, user_id: int) -> Transaction:
    return Transaction(
        transactionId=row["id"],
        date=datetime.fromisoformat(row["date"]),
        transactionType=TransactionType(row["type"]),
        description=row["description"],
        amount=row["amount"],
        currency=row["currency"],
        account=row["account"],
        sourceFile=row["source_file"],
        category=row["category"],
        user_id=user_id,
    )


def stage_import(user_id: int, files: list[tuple[str, str]], run_llm: bool | None = None) -> dict:
    """files: [(name shown to the user, saved path)]. Returns the preview."""
    run_llm = settings.ENABLE_LLM_CATEGORIZATION if run_llm is None else run_llm
    file_results, staged, seen = [], [], set()

    for index, (name, path) in enumerate(files):
        try:
            transactions, excluded, config = parse_transactions(path, user_id)
        except UnknownFormat as exc:
            file_results.append({"filename": name, "error": str(exc)})
            continue
        except Exception as exc:
            file_results.append({"filename": name, "error": f"Could not read this file: {exc}"})
            continue

        new, existing, repeated = split_new(
            transactions, existing_ids(user_id, [t.transactionId for t in transactions]), seen
        )
        file_results.append({
            "filename": name,
            "format": f"{config['bank'].upper()} · {config['file_type']}",
            "parsed": len(transactions),
            "excluded": excluded,
            "already_imported": existing,
            "duplicate_in_upload": repeated,
            "new": len(new),
        })
        staged.extend((index, t) for t in new)

    # Categorize only the rows that would be added, all files in one go.
    sources = categorize_transactions([t for _, t in staged], user_id, run_llm=run_llm)
    rows = [_serialize(t, index, sources.get(t.transactionId)) for index, t in staged]

    import_id = _save_staged(user_id, file_results, rows)
    return {"import_id": import_id, "files": file_results, "transactions": rows}


def _save_staged(user_id: int, files: list[dict], rows: list[dict]) -> str:
    import_id = uuid.uuid4().hex
    with engine.connect() as conn:
        # Previews nobody confirmed or cancelled (closed tab...) expire.
        conn.execute(
            text("DELETE FROM staged_imports WHERE user_id = :user_id AND created_at < NOW() - make_interval(hours => :ttl)"),
            {"user_id": user_id, "ttl": STAGED_IMPORT_TTL_HOURS}
        )
        conn.execute(
            text("""
                INSERT INTO staged_imports (id, user_id, files, transactions)
                VALUES (:id, :user_id, CAST(:files AS JSONB), CAST(:transactions AS JSONB))
            """),
            {"id": import_id, "user_id": user_id, "files": json.dumps(files), "transactions": json.dumps(rows)}
        )
        conn.commit()
    return import_id


def _load_staged(user_id: int, import_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT files, transactions FROM staged_imports WHERE id = :id AND user_id = :user_id"),
            {"id": import_id, "user_id": user_id}
        ).mappings().first()
    return dict(row) if row else None


def discard_import(user_id: int, import_id: str) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text("DELETE FROM staged_imports WHERE id = :id AND user_id = :user_id"),
            {"id": import_id, "user_id": user_id}
        )
        conn.commit()
        return result.rowcount > 0


def summarize_commit(files: list[dict], rows: list[dict], selected: set[str], inserted: set[str]) -> list[dict]:
    """Per-file results after importing: what was added, left out by the user,
    or turned out to exist already (imported elsewhere since the preview)."""
    results = []
    for index, f in enumerate(files):
        if f.get("error"):
            results.append(f)
            continue
        mine = [r for r in rows if r["file"] == index]
        added = [r for r in mine if r["id"] in inserted]
        results.append({
            **f,
            "added": len(added),
            "not_selected": sum(1 for r in mine if r["id"] not in selected),
            "already_imported": f["already_imported"] + sum(1 for r in mine if r["id"] in selected and r["id"] not in inserted),
            "rule_matched": sum(1 for r in added if r["category_source"] == "rule"),
            "llm_matched": sum(1 for r in added if r["category_source"] == "llm"),
        })
    return results


def commit_import(user_id: int, import_id: str, selected_ids: list[str] | None = None) -> dict | None:
    """Insert the staged rows (all, or only selected_ids). None if the import doesn't exist."""
    staged = _load_staged(user_id, import_id)
    if staged is None:
        return None
    rows = staged["transactions"]
    selected = {r["id"] for r in rows} if selected_ids is None else set(selected_ids)

    inserted = insert_transactions([_deserialize(r, user_id) for r in rows if r["id"] in selected])
    discard_import(user_id, import_id)

    files = summarize_commit(staged["files"], rows, selected, inserted)
    return {"files": files, "added": len(inserted)}
