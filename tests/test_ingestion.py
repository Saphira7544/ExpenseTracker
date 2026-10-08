from datetime import datetime

import pytest

from app.services import ingestion
from models.transaction import Transaction, TransactionType


def tx(tid, amount=-10.0, desc="Coop"):
    return Transaction(transactionId=tid, date=datetime(2026, 3, 5), transactionType=TransactionType.DEBIT,
                       description=desc, amount=amount, currency="CHF", account="UBS Debit", sourceFile="ubs.csv")


def test_split_new_counts_existing_and_repeated_rows():
    seen = set()
    new, existing, repeated = ingestion.split_new([tx("a"), tx("b"), tx("c")], {"b"}, seen)
    assert [t.transactionId for t in new] == ["a", "c"] and (existing, repeated) == (1, 0)

    # a second file in the same upload overlapping the first
    new, existing, repeated = ingestion.split_new([tx("c"), tx("d")], set(), seen)
    assert [t.transactionId for t in new] == ["d"] and (existing, repeated) == (0, 1)


def test_serialize_round_trip():
    original = tx("a")
    original.category = "Groceries"
    row = ingestion._serialize(original, file_index=0, category_source="rule")
    back = ingestion._deserialize(row, user_id=7)
    assert (back.transactionId, back.date, back.amount, back.category, back.user_id) == ("a", datetime(2026, 3, 5), -10.0, "Groceries", 7)
    assert back.transactionType is TransactionType.DEBIT


def test_summarize_commit():
    files = [
        {"filename": "a.csv", "parsed": 5, "excluded": 1, "already_imported": 1, "duplicate_in_upload": 0, "new": 3},
        {"filename": "bad.csv", "error": "No bank format recognises this file."},
    ]
    rows = [
        {"id": "1", "file": 0, "category_source": "rule"},
        {"id": "2", "file": 0, "category_source": "llm"},
        {"id": "3", "file": 0, "category_source": None},
    ]
    # user unticked row 3; row 2 got imported by someone/something else in the meantime
    result = ingestion.summarize_commit(files, rows, selected={"1", "2"}, inserted={"1"})
    assert result[0]["added"] == 1
    assert result[0]["not_selected"] == 1
    assert result[0]["already_imported"] == 2
    assert (result[0]["rule_matched"], result[0]["llm_matched"]) == (1, 0)
    assert result[1] == files[1]


@pytest.fixture
def staged_ingestion(monkeypatch, tmp_path):
    """stage/commit with parsing real but the database replaced by in-memory fakes."""
    staged, inserted_rows = {}, []
    monkeypatch.setattr(ingestion, "detection_configs", lambda uid: None)  # built-in defaults
    monkeypatch.setattr(ingestion, "get_exclusion_patterns", lambda uid, bank: ["Payment to card"])
    monkeypatch.setattr(ingestion, "existing_ids", lambda uid, ids: {"TX1"})
    monkeypatch.setattr(ingestion, "rule_based_categorize",
                        lambda ts, uid: [setattr(t, "category", "Salary") for t in ts if "ACME" in t.description])
    monkeypatch.setattr(ingestion, "classify_transactions_batch", lambda descs: ["Groceries"] * len(descs))
    monkeypatch.setattr(ingestion, "_save_staged", lambda uid, files, rows: staged.setdefault("x", {"files": files, "transactions": rows}) and "x")
    monkeypatch.setattr(ingestion, "_load_staged", lambda uid, iid: staged.get(iid))
    monkeypatch.setattr(ingestion, "discard_import", lambda uid, iid: staged.pop(iid, None) is not None)
    monkeypatch.setattr(ingestion, "insert_transactions",
                        lambda ts: inserted_rows.extend(ts) or {t.transactionId for t in ts})

    from tests.test_parser import UBS_DEBIT
    good = tmp_path / "ubs.csv"
    good.write_bytes(UBS_DEBIT.encode("latin1"))
    bad = tmp_path / "other.csv"
    bad.write_text("just,some,columns\n1,2,3\n")
    return [("ubs.csv", str(good)), ("other.csv", str(bad))], staged, inserted_rows


def test_stage_then_commit(staged_ingestion):
    files, staged, inserted_rows = staged_ingestion
    preview = ingestion.stage_import(7, files, run_llm=True)

    ubs, other = preview["files"]
    assert other["error"].startswith("No bank format")
    assert (ubs["parsed"], ubs["excluded"], ubs["already_imported"], ubs["new"]) == (2, 1, 1, 1)
    assert [(r["id"], r["category"], r["category_source"]) for r in preview["transactions"]] == [("TX3", "Salary", "rule")]
    assert inserted_rows == []  # nothing added by the preview

    result = ingestion.commit_import(7, preview["import_id"], ["TX3"])
    assert result["added"] == 1 and [t.transactionId for t in inserted_rows] == ["TX3"]
    assert inserted_rows[0].user_id == 7
    assert staged == {}  # staging cleaned up
    assert ingestion.commit_import(7, preview["import_id"]) is None  # can't import twice


def test_llm_only_sees_new_rows(staged_ingestion, monkeypatch):
    files, _, _ = staged_ingestion
    seen = []
    monkeypatch.setattr(ingestion, "rule_based_categorize", lambda ts, uid: None)
    monkeypatch.setattr(ingestion, "classify_transactions_batch", lambda descs: seen.extend(descs) or ["Other"] * len(descs))
    preview = ingestion.stage_import(7, files, run_llm=True)
    assert len(seen) == 1  # TX1 was already imported and TX2 excluded: neither sent to the LLM
    assert preview["transactions"][0]["category_source"] == "llm"
