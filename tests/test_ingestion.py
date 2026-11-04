from types import SimpleNamespace
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
    monkeypatch.setattr(ingestion, "classify_transactions_batch", lambda descs, categories, key: (["Groceries"] * len(descs), None))
    monkeypatch.setattr(ingestion, "get_api_key", lambda uid: "key")
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


STAGED_ROW = {
    "id": "TX9", "file": 0, "date": "2026-03-05", "type": "debit", "description": "Migros Zurich", "amount": -12.5,
    "currency": "CHF", "account": "UBS Debit", "source_file": "ubs.csv", "category": "Groceries", "category_source": "llm",
}


def test_edits_change_only_what_was_edited():
    other = {**STAGED_ROW, "id": "TX8"}
    edited, untouched = ingestion.apply_edits([STAGED_ROW, other], {"TX9": {"description": "Migros"}})
    assert edited["description"] == "Migros" and edited["category_source"] == "llm" and edited["amount"] == -12.5
    assert untouched == other
    assert STAGED_ROW["description"] == "Migros Zurich"  # the staged row itself isn't changed


def test_a_category_edited_in_the_review_is_manual_and_survives_rules():
    [row] = ingestion.apply_edits([STAGED_ROW], {"TX9": {"category": "Health"}})
    t = ingestion._deserialize(row, 7)
    assert t.category == "Health" and t.is_manual_category is True
    assert ingestion._deserialize(STAGED_ROW, 7).is_manual_category is False


def test_clearing_a_category_leaves_it_for_the_rules():
    [row] = ingestion.apply_edits([STAGED_ROW], {"TX9": {"category": None}})
    t = ingestion._deserialize(row, 7)
    assert t.category is None and t.is_manual_category is False


def test_flipping_an_amount_updates_the_type():
    [row] = ingestion.apply_edits([STAGED_ROW], {"TX9": {"amount": 12.5}})
    assert ingestion._deserialize(row, 7).transactionType.value == "credit"


def test_commit_stores_the_edits(staged_ingestion):
    files, _, inserted_rows = staged_ingestion
    preview = ingestion.stage_import(7, files, run_llm=True)
    result = ingestion.commit_import(7, preview["import_id"], ["TX3"], {"TX3": {"category": "Health", "date": "2026-04-01"}})
    assert result["added"] == 1
    t = inserted_rows[0]
    assert (t.transactionId, t.category, t.is_manual_category) == ("TX3", "Health", True)
    assert t.date.date().isoformat() == "2026-04-01"
    assert result["files"][0]["rule_matched"] == 0  # no longer the rule's doing


def test_llm_only_sees_new_rows(staged_ingestion, monkeypatch):
    files, _, _ = staged_ingestion
    seen = []
    monkeypatch.setattr(ingestion, "rule_based_categorize", lambda ts, uid: None)
    monkeypatch.setattr(ingestion, "classify_transactions_batch", lambda descs, categories, key: (seen.extend(descs) or ["Other"] * len(descs), None))
    preview = ingestion.stage_import(7, files, run_llm=True)
    assert len(seen) == 1  # TX1 was already imported and TX2 excluded: neither sent to the LLM
    assert preview["transactions"][0]["category_source"] == "llm"


def test_preview_says_when_the_ai_failed(staged_ingestion, monkeypatch):
    files, _, _ = staged_ingestion
    monkeypatch.setattr(ingestion, "rule_based_categorize", lambda ts, uid: None)
    monkeypatch.setattr(ingestion, "classify_transactions_batch",
                        lambda descs, categories, key: ([None] * len(descs), "No credits left."))
    preview = ingestion.stage_import(7, files, run_llm=True)
    assert preview["ai_warning"] == {"message": "No credits left.", "uncategorized": 1}
    assert preview["transactions"][0]["category"] is None


def test_preview_has_no_warning_when_the_ai_worked(staged_ingestion):
    files, _, _ = staged_ingestion
    assert ingestion.stage_import(7, files, run_llm=True)["ai_warning"] is None


class FakeConnection:
    """Answers the SELECT with `rows` and records the UPDATE."""
    def __init__(self, rows, updates):
        self.rows, self.updates = rows, updates

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        if str(statement).strip().startswith("UPDATE"):
            self.updates.extend(params)
        return self

    def all(self):
        return self.rows

    def commit(self):
        pass


@pytest.fixture
def uncategorized(monkeypatch):
    updates = []
    rows = [("A", "Migros"), ("B", "Mystery shop"), ("C", "Another mystery")]
    monkeypatch.setattr(ingestion, "engine", SimpleNamespace(connect=lambda: FakeConnection(rows, updates)))
    monkeypatch.setattr(ingestion, "rule_based_categorize",
                        lambda ts, uid: [setattr(t, "category", "Groceries") for t in ts if t.description == "Migros"])
    monkeypatch.setattr(ingestion, "get_api_key", lambda uid: "key")
    return updates


def test_rerun_uses_rules_then_ai_and_saves_only_what_it_found(uncategorized, monkeypatch):
    seen = []
    monkeypatch.setattr(ingestion, "classify_transactions_batch",
                        lambda descs, categories, key: (seen.extend(descs) or ["Other", None], None))
    result = ingestion.categorize_uncategorized(7)
    assert seen == ["Mystery shop", "Another mystery"]
    assert result == {"total": 3, "categorized": 2, "by_rule": 1, "by_ai": 1, "problem": None}
    assert {u["id"]: u["category"] for u in uncategorized} == {"A": "Groceries", "B": "Other"}


def test_rerun_reports_why_the_ai_failed(uncategorized, monkeypatch):
    monkeypatch.setattr(ingestion, "classify_transactions_batch",
                        lambda descs, categories, key: ([None] * len(descs), "No credits left."))
    result = ingestion.categorize_uncategorized(7)
    assert result["problem"] == "No credits left." and result["by_ai"] == 0 and result["categorized"] == 1


def test_rerun_says_when_the_ai_is_turned_off(uncategorized, monkeypatch):
    monkeypatch.setattr(ingestion.settings, "ENABLE_LLM_CATEGORIZATION", False)
    assert "turned off" in ingestion.categorize_uncategorized(7)["problem"]
