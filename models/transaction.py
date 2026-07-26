from dataclasses import dataclass
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
    is_manual_category: bool = False
    user_id: Optional[int] = None
    
