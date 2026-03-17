from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

class TransactionType(Enum):
    DEBIT = "debit"
    CREDIT = "credit"
    NULL = "null"

@dataclass
class Transaction:
    transactionId: str
    date: datetime
    transactionType: TransactionType
    description: str
    amount: float
    currency: str
    account: str
    sourceFile: str
    category: Optional[str] = None
    
