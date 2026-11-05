from app.services.transactions import _filter_clause


def test_uncategorized_finds_transactions_with_no_category():
    where, params = _filter_clause(7, category="Uncategorized")
    assert "category IS NULL OR category = ''" in where
    assert "category" not in params


def test_a_normal_category_is_matched_by_name():
    where, params = _filter_clause(7, category="Groceries")
    assert "category = :category" in where and params["category"] == "Groceries"


def test_no_category_filter_means_everything():
    where, params = _filter_clause(7)
    assert "category" not in where and params == {"user_id": 7}
