from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class TransactionType(Enum):
    DEBIT = "debit"
    CREDIT = "credit"
    NULL = "NULL"

@dataclass
class Transaction:
    transactionId: str
    transactionType: TransactionType
    date: str
    description: str
    amount: float
    currency: str
    account: str
    sourceFile: str
    category: str
    
