import pandas as pd
import os
import hashlib
from typing import List, Dict, Any
from abc import ABC, abstractmethod
from utils.file_utils import read_file_lines
from models.transaction import Transaction, TransactionType  

class BaseParser(ABC):
    @abstractmethod
    def parse(self, filepath: str) -> List[Transaction]:
        pass

class GenericParser(BaseParser):
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def parse(self, filepath: str) -> List[Transaction]:
        return self._parse_file(filepath, self.config)

    def _parse_file(self, filepath: str, config: Dict[str, Any]) -> List[Transaction]:

        skiprows = self._get_skiprows(read_file_lines(filepath), config.get('header', ''))
        sep = config.get('sep', ';')  # Use config or default ;     
        df = pd.read_csv(filepath, sep=sep, skiprows=skiprows, encoding=config.get('encoding', 'latin1'), dtype=str, on_bad_lines='skip')
        df = df.fillna('').dropna(how='all')  # Clean NaNs/empty

        # Dates
        date_col = config['date_col']
        df['date'] = pd.to_datetime(df[date_col], format=config.get('date_format'), errors='coerce')

        # Descriptions
        desc_cols = config['desc_cols']
        if isinstance(desc_cols, list):
            df['description'] = df[desc_cols].agg(' '.join, axis=1).str.strip()
        else:
            df['description'] = df[desc_cols].str.strip()

        # Filter
        df = self._apply_exclusions(df, config)

        # Amount/Type
        if 'debit_col' in config:
            df[['amount', 'transactionType']] = df.apply(
                lambda row: self._parse_amount(row, config['debit_col'], config['credit_col']), axis=1, result_type='expand'
            )
            if config.get('drop_empty_amount', True):
                df = df[df['transactionType'] != TransactionType.NULL.value]

        else:  # TODO: Make more flexible -> currently assumes single-amount column is always a debit
            df['amount'] = pd.to_numeric(df[config['amount_col']], errors='coerce') * -1  # Negative debits
            df['transactionType'] = TransactionType.DEBIT.value

        # Other fields
        df['currency'] = df[config['currency_col']].str.strip()
        df['account'] = config['account']
        df['sourceFile'] = os.path.basename(filepath)

        # Drop invalid rows
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df = df.dropna(subset=['date', 'amount'])

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
        """Return the index of the first line containing any of the header signatures.  
                -> pandas skips everything before the returned index and reads the rest as columns."""
        signatures = header if isinstance(header, list) else [header]
        for i, line in enumerate(lines):
            if any(sig in line for sig in signatures):
                return i  # Skip i rows; line i becomes the pandas header
        return 0

    @staticmethod
    def _parse_amount(row: pd.Series, debit_col: str, credit_col: str) -> tuple:
        debit_raw = row.get(debit_col, '').strip()
        credit_raw = row.get(credit_col, '').strip()
        
        if debit_raw:
            amount = abs(float(debit_raw)) * -1  # Always negative 
            return amount, TransactionType.DEBIT.value
        if credit_raw:
            amount = abs(float(credit_raw))      # Always positive
            return amount, TransactionType.CREDIT.value
        
        return 0.0, TransactionType.NULL.value

    @staticmethod
    def _generate_id(date, desc: str, amt: float) -> str:
        date_str = date.strftime('%Y%m%d') if pd.notna(date) else 'unknown'
        key = f"{date_str}-{str(desc)[:50]}-{amt}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    @staticmethod
    def _apply_exclusions(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """ Excludes transactions with certain descriptions """

        exclude_patterns = config.get('exclude_patterns', [])
        if not exclude_patterns:
            return df

        is_excluded = df['description'].str.contains(
            '|'.join(exclude_patterns), case=False, na=False
        )
        dropped = is_excluded.sum()
        df = df[~is_excluded]
        print(f"Excluded {dropped} rows matching exclusion patterns")
        return df
