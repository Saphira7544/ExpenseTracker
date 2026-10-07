from parsers.detector import detect_config
from parsers.generic_parser import GenericParser

UBS_DEBIT = """Account number:;0000 00000000.0;
Trade date;Trade time;Booking date;Value date;Currency;Debit;Credit;Individual amount;Balance;Transaction no.;Description1;Description2;Description3;Footnotes;
2026-03-05;;2026-03-05;2026-03-05;CHF;-12.50;;;;TX1;Migros;Zurich;Debit card payment;;
2026-03-05;;2026-03-05;2026-03-05;CHF;-200.00;;;;TX2;Own account;Payment to card;;;
2026-03-06;;2026-03-06;2026-03-06;CHF;;5000.00;;;TX3;ACME AG;Salary;;;
"""

CGD_DEBIT = """Data mov. ;Data valor ;Descrição;Débito ;Crédito;Saldo contabilístico;Saldo disponível ;Categoria
05-03-2026;05-03-2026;CAFE CENTRAL;3,50;;100,00;100,00;
05-03-2026;05-03-2026;CAFE CENTRAL;3,50;;96,50;96,50;
06-03-2026;06-03-2026;CAFE CENTRAL;3,50;;93,00;93,00;
"""


def write(tmp_path, name, content):
    path = tmp_path / name
    path.write_bytes(content.encode("latin1"))
    return str(path)


def test_exclusion_patterns_come_from_the_caller(tmp_path):
    path = write(tmp_path, "ubs.csv", UBS_DEBIT)
    config = detect_config(path)
    assert config["bank"] == "ubs"

    everything = GenericParser(config).parse(path)
    assert len(everything) == 3

    parser = GenericParser(config, ["payment to CARD"])  # case-insensitive
    kept = parser.parse(path)
    assert [t.transactionId for t in kept] == ["TX1", "TX3"]
    assert parser.excluded_count == 1
    assert kept[0].amount == -12.5 and kept[1].amount == 5000.0


def test_identical_rows_on_the_same_day_get_distinct_ids(tmp_path):
    path = write(tmp_path, "cgd.csv", CGD_DEBIT)
    transactions = GenericParser(detect_config(path)).parse(path)
    ids = [t.transactionId for t in transactions]
    assert len(ids) == 3 and len(set(ids)) == 3
    assert all(t.currency == "EUR" and t.amount == -3.5 for t in transactions)
