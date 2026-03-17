
UBS_CONFIGS = {
    "debit": {
        "header": "Trade date",
        "date_col": "Value date",
        "date_format": "%Y-%m-%d",
        "desc_cols": ["Description1", "Description2", "Description3"],  # Multi-col
        "debit_col": "Debit",
        "credit_col": "Credit",
        "currency_col": "Currency",
        "id_col": "Transaction no.",
        "account": "UBS Debit",
        "sep": ";"
    },
    "prepaid": {
        "header": "Account number",
        "date_col": "Purchase date",
        "date_format": "%d.%m.%Y",
        "desc_cols": "Booking text",
        "amount_col": "Amount",  # Single amount col
        "currency_col": "Currency",
        "id_col": None,
        "account": "UBS Prepaid",
        "sep": ";"
    }
}

# REVOLUT_CONFIGS = { ... }

# CGD_CONFIGS = { ... }
