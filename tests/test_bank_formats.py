import pytest
from pydantic import ValidationError

from app.api.routes.bank_formats import BankFormatPayload, preview_file
from app.services.bank_formats import normalize_config
from parsers.detector import default_formats, detect_config
from parsers.generic_parser import GenericParser
from utils.number_utils import to_float

REVOLUT = """Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance
CARD_PAYMENT,Current,2026-03-05 10:00:00,2026-03-06 09:00:00,Café Zürich,-12.50,0.00,CHF,COMPLETED,100.00
TOPUP,Current,2026-03-07 08:00:00,2026-03-07 08:00:00,Top-up by *1234,"1,200.00",0.00,CHF,COMPLETED,1300.00
"""

REVOLUT_FORMAT = {
    "bank": " Revolut ",
    "file_type": "main",
    "account": "Revolut Main",
    "header": ["Started Date", "Completed Date", ""],
    "sep": ",",
    "encoding": "utf-8",
    "date_col": "Started Date",
    "date_format": "%Y-%m-%d %H:%M:%S",
    "desc_cols": ["Description"],
    "amount_mode": "single",
    "amount_col": "Amount",
    "currency_col": "Currency",
}


@pytest.fixture
def revolut_file(tmp_path):
    path = tmp_path / "revolut.csv"
    path.write_text(REVOLUT, encoding="utf-8")
    return str(path)


def test_payload_normalises_and_derives_config():
    config = BankFormatPayload(**REVOLUT_FORMAT).to_config()
    assert config["bank"] == "revolut"
    assert config["header"] == ["Started Date", "Completed Date"]
    assert config["debit_col"] is None and config["amount_col"] == "Amount"


@pytest.mark.parametrize("change, message", [
    ({"amount_col": None}, "amount column is required"),
    ({"amount_mode": "debit_credit"}, "debit and credit columns are required"),
    ({"currency_col": None}, "currency column or a fixed currency"),
    ({"header": ["  "]}, "add at least one"),
    ({"encoding": "klingon"}, "unknown encoding"),
    ({"sep": ":"}, "choose"),
    ({"bank": "UBS/Card!"}, "letters, numbers"),
    ({"date_format": "dd.mm.yyyy"}, "%d.%m.%Y"),
    ({"fixed_currency": "francs", "currency_col": None}, "3-letter"),
])
def test_payload_validation(change, message):
    with pytest.raises(ValidationError) as exc:
        BankFormatPayload(**{**REVOLUT_FORMAT, **change})
    assert message in str(exc.value)


def test_single_signed_amount_column(revolut_file):
    config = BankFormatPayload(**REVOLUT_FORMAT).to_config()
    transactions = GenericParser(config).parse(revolut_file)
    assert [t.amount for t in transactions] == [-12.5, 1200.0]          # "1,200.00" thousands separator
    assert [t.transactionType.value for t in transactions] == ["debit", "credit"]
    assert transactions[0].description == "Café Zürich"                  # utf-8 read correctly

    flipped = GenericParser({**config, "invert_amount": True}).parse(revolut_file)
    assert [t.amount for t in flipped] == [12.5, -1200.0]


def test_detection_uses_each_formats_encoding(revolut_file):
    revolut = BankFormatPayload(**{**REVOLUT_FORMAT, "header": ["Café"]}).to_config()
    assert detect_config(revolut_file, [revolut])["bank"] == "revolut"
    with pytest.raises(ValueError):
        detect_config(revolut_file, [{**revolut, "encoding": "latin1"}])  # "Café" decodes differently
    with pytest.raises(ValueError):
        detect_config(revolut_file, [{**revolut, "header": []}])          # no signatures never matches


def test_built_in_defaults_normalise_cleanly():
    configs = [normalize_config(c) for c in default_formats()]
    by_key = {(c["bank"], c["file_type"]): c for c in configs}
    ubs = by_key[("ubs", "prepaid")]
    assert ubs["desc_cols"] == ["Booking text"]
    assert ubs["amount_col"] is None and ubs["debit_col"] == "Debit"
    assert all(not h.endswith(" ") for c in configs for h in c["header"])
    for c in configs:  # every default passes the same validation as the Banks dialog
        mode = "single" if c["amount_col"] else "debit_credit"
        BankFormatPayload(**{**c, "amount_mode": mode})


def test_to_float_thousands_separators():
    assert to_float("1'234.50") == 1234.5
    assert to_float("1,234.50") == 1234.5
    assert to_float("1.234,50", ",") == 1234.5
    assert to_float("-12.50") == -12.5


def test_preview_with_incomplete_and_complete_format(revolut_file):
    partial = preview_file(revolut_file, {"sep": ",", "encoding": "utf-8"}, saved_configs=[])
    assert "Amount" in partial["columns"] and partial["raw_rows"]
    assert partial["transactions"] == [] and "Fill in the format" in partial["error"]

    full = preview_file(revolut_file, REVOLUT_FORMAT, saved_configs=[])
    assert full["header_found"] and full["error"] is None
    assert full["total"] == 2 and full["transactions"][0]["amount"] == -12.5
    assert full["detected"] is None

    saved = [BankFormatPayload(**REVOLUT_FORMAT).to_config()]
    assert preview_file(revolut_file, REVOLUT_FORMAT, saved)["detected"] == "REVOLUT · main"

    wrong_col = preview_file(revolut_file, {**REVOLUT_FORMAT, "amount_col": "Betrag"}, saved_configs=[])
    assert "Betrag" in wrong_col["error"] and "Columns found" in wrong_col["error"]


def test_suggests_separator_and_encoding(revolut_file, tmp_path):
    from app.api.routes.bank_formats import suggest_file_settings
    assert suggest_file_settings(revolut_file) == {"encoding": "utf-8", "sep": ","}
    latin = tmp_path / "cgd.csv"
    latin.write_bytes("Data mov.;Descrição;Débito\n05-03-2026;CAFÉ;3,50\n".encode("latin1"))
    assert suggest_file_settings(str(latin)) == {"encoding": "latin1", "sep": ";"}


def test_category_roles_must_not_overlap():
    from app.services.settings import validate_settings, DEFAULT_SETTINGS
    assert validate_settings(dict(DEFAULT_SETTINGS)) is None
    clash = {**DEFAULT_SETTINGS, "ignored_categories": ["Internal", "Salary"]}
    assert "only have one role" in validate_settings(clash)
    assert "Unknown" in validate_settings({**DEFAULT_SETTINGS, "ignored_categories": ["Nope"]})


def test_every_category_has_a_fixed_colour():
    from app.core.categories import CATEGORIES, CATEGORY_COLORS
    import re
    missing = [c for c in CATEGORIES + ["Uncategorized", "Split"] if c not in CATEGORY_COLORS]
    assert missing == []
    assert all(re.fullmatch(r"#[0-9a-f]{6}", v) for v in CATEGORY_COLORS.values())
    assert len(set(CATEGORY_COLORS.values())) == len(CATEGORY_COLORS)  # no two categories share a colour
