import pandas as pd
import os
import hashlib
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime
from models.transaction import Transaction, TransactionType  # Fix your dataclass import

class BaseParser(ABC):
    @abstractmethod
    def parse(self, filepath: str) -> List[Transaction]:
        pass

class GenericParser(BaseParser):
    def __init__(self, configs: Dict[str, Dict[str, Any]]):
        self.configs = configs

    def parse(self, filepath: str) -> List[Transaction]:
        lines = self._read_lines(filepath)
        config = self._detect_config(lines)
        if not config:
            raise ValueError(f"Unknown file format: {filepath}")
        return self._parse_file(filepath, config)

    def _read_lines(self, filepath: str) -> List[str]:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.readlines()

    def _detect_config(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        for subtype, c in self.configs.items():
            if c.get('header') and any(c['header'] in line for line in lines[:20]):  # Scan first 20 lines
                return {**c, 'subtype': subtype}
        return None

    def _parse_file(self, filepath: str, config: Dict[str, Any]) -> List[Transaction]:
        # Robust CSV: Auto-detect sep, skip messy header/metadata
        skiprows = self._get_skiprows(self._read_lines(filepath), config.get('header', ''))
        sep = config.get('sep', ';')  # Default semicolon for UBS     
        df = pd.read_csv(filepath, sep=sep, skiprows=skiprows, encoding='utf-8', dtype=str, on_bad_lines='skip')
        df = df.fillna('').dropna(how='all')  # Clean NaNs/empty

        # Dates
        date_col = config['date_col']
        df['date'] = pd.to_datetime(df[date_col], format=config.get('date_format'), errors='coerce')

        # Descriptions: Multi-col join
        desc_cols = config['desc_cols']
        if isinstance(desc_cols, list):
            df['description'] = df[desc_cols].agg(' '.join, axis=1).str.strip()
        else:
            df['description'] = df[desc_cols].str.strip()

        # Amount/Type
        if 'debit_col' in config:
            df[['amount', 'transactionType']] = df.apply(
                lambda row: self._parse_amount(row, config['debit_col'], config['credit_col']), axis=1, result_type='expand'
            )
        else:  # Prepaid: Use Amount col, assume debit
            df['amount'] = pd.to_numeric(df[config['amount_col']], errors='coerce') * -1  # Negative debits
            df['transactionType'] = TransactionType.DEBIT.value

        # Other fields
        df['currency'] = df[config['currency_col']].str.strip()
        df['account'] = config['account']
        df['sourceFile'] = os.path.basename(filepath)

        # Drop invalid rows
        df = df.dropna(subset=['date', 'amount'])
        df = df[df['amount'].astype(str).str.strip() != '']

        # Generate IDs
        df['transactionId'] = df[config.get('id_col', '')] \
            .str.strip() if config.get('id_col') and config['id_col'] in df.columns else \
            df.apply(lambda row: GenericParser._generate_id(row['date'], row['description'], row['amount']), axis=1)

        transactions = []
        for _, row in df.iterrows():
            transactions.append(Transaction(
                transactionId=str(row['transactionId']),
                date=row['date'],
                transactionType=TransactionType(row['transactionType']),
                description=str(row['description']),
                amount=float(row['amount']),
                currency=str(row['currency']),
                account=str(row['account']),
                sourceFile=str(row['sourceFile']),
                category=None
            ))
        return transactions

    @staticmethod
    def _get_skiprows(lines: List[str], header: str) -> int:
        """Return the index of the header row — pandas skips everything before it and reads it as columns."""
        for i, line in enumerate(lines):
            if header in line:
                return i  # Skip i rows; line i becomes the pandas header
        return 0


    @staticmethod
    def _parse_amount(row: pd.Series, debit_col: str, credit_col: str) -> tuple:
        debit = row.get(debit_col, '').strip()
        credit = row.get(credit_col, '').strip()
        if debit:
            return -float(debit), TransactionType.DEBIT.value
        if credit:
            return float(credit), TransactionType.CREDIT.value
        return 0.0, TransactionType.NULL.value

    @staticmethod
    def _generate_id(date, desc: str, amt: float) -> str:
        date_str = date.strftime('%Y%m%d') if pd.notna(date) else 'unknown'
        key = f"{date_str}-{str(desc)[:50]}-{amt}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

