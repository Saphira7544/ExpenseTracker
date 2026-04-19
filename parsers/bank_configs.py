
UBS_CONFIGS = {
    "debit": {
        "bank": "ubs",
        "file_type": "debit",
        "header": "Trade date",
        "sep": ";",
        "encoding": "latin1",
        "date_col": "Value date",
        "date_format": "%Y-%m-%d",
        "desc_cols": ["Description1", "Description2", "Description3"],  # Multi-col
        "debit_col": "Debit",
        "credit_col": "Credit",
        "currency_col": "Currency",
        "id_col": "Transaction no.",
        "account": "UBS Debit"
        
    },
    "prepaid": {
        "bank": "ubs",
        "file_type": "prepaid",
        "header": "Account number",
        "sep": ";",
        "encoding": "latin1",
        "date_col": "Purchase date",
        "date_format": "%d.%m.%Y",
        "desc_cols": "Booking text",
        "debit_col": "Debit",
        "credit_col": "Credit",
        #"amount_col": "Amount",  # Single amount col
        "currency_col": "Currency",
        "id_col": None,
        "account": "UBS Prepaid"
    }
}

# REVOLUT_CONFIGS = { ... }

# CGD_CONFIGS = { ... }

ALL_BANK_CONFIGS = [
    *UBS_CONFIGS.values(),
]