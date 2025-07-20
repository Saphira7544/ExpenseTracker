from dataclasses import dataclass
from datetime import datetime

@dataclass
class Transaction:
    date: datetime
    description: str
    amount: float
    currency: str
    account: str
    source_file: str
