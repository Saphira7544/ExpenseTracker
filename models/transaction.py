from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class TransactionType(Enum):
    DEBIT = "debit"
    CREDIT = "credit"
    NULL = "NULL"

@dataclass
class Transaction:
    date: str
    description: str
    amount: float
    currency: str
    account: str
    source_file: str
    transaction_type: TransactionType
