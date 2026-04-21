
UBS_CONFIGS = {
    "_bank_exclude_patterns": [
        "Revolut",                  # Revolut top-ups (any account)        
        "I. PEREIRA CASTELO",       # My name = internal
        "Payment to card",          # Debit -> prepaid
        "TRANSFER FROM ACCOUNT"     # Prepaid <- Debit     
    ],
    "debit": {
        "bank": "ubs",
        "file_type": "debit",
        "header": ["Trade date", "Transaction no.", "Value date"],
        "sep": ";",
        "encoding": "latin1",
        "date_col": "Value date",
        "date_format": "%Y-%m-%d",
        "desc_cols": ["Description1", "Description2", "Description3"],  # Multi-col
        "debit_col": "Debit",
        "credit_col": "Credit",
        "currency_col": "Currency",
        "fixed_currency": None,
        "id_col": "Transaction no.",
        "account": "UBS Debit",
        "drop_empty_amount": True,
        "decimal_sep": "."
        
    },
    "prepaid": {
        "bank": "ubs",
        "file_type": "prepaid",
        "header": ["Account number", "Purchase date", "Booking text"],
        "sep": ";",
        "encoding": "latin1",
        "date_col": "Purchase date",
        "date_format": "%d.%m.%Y",
        "desc_cols": "Booking text",
        "debit_col": "Debit",
        "credit_col": "Credit",
        #"amount_col": "Amount",  # Single amount col
        "currency_col": "Currency",
        "fixed_currency": None,
        "id_col": None,
        "account": "UBS Prepaid",
        "drop_empty_amount": True,
        "decimal_sep": "."
    }
}

# REVOLUT_CONFIGS = { ... }

CGD_CONFIGS = {
    "_bank_exclude_patterns": [       
    ],

    "debit": {
        "bank": "cgd",
        "file_type": "debit",
        "header": ["Data mov. ", "Débito ", "Saldo disponível "],
        "sep": ";",
        "encoding": "latin1",
        "date_col": "Data valor ",
        "date_format": "%d-%m-%Y",
        "desc_cols": ["Descrição"],  # Multi-col
        "debit_col": "Débito ",
        "credit_col": "Crédito",
        "currency_col": None,
        "fixed_currency": "EUR",
        "id_col": None,
        "account": "CGD Debit",
        "drop_empty_amount": True,
        "decimal_sep": ","
    },
}    

ALL_BANK_CONFIGS = {
    "ubs": UBS_CONFIGS,
    "cgd": CGD_CONFIGS,
}