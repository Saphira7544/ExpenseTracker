import pandas as pd
import os, re
import hashlib
from typing import List, Dict, Any
from abc import ABC, abstractmethod
from utils.file_utils import read_file_lines
from utils.number_utils import to_float
from models.transaction import Transaction, TransactionType  

class BaseParser(ABC):
    @abstractmethod
    def parse(self, filepath: str) -> List[Transaction]:
        pass

class GenericParser(BaseParser):
    def __init__(self, config: Dict[str, Any]):
        self.config = {k: self._clean_config_value(v) for k, v in config.items()}

    def parse(self, filepath: str) -> List[Transaction]:
        return self._parse_file(filepath, self.config)

    def _parse_file(self, filepath: str, config: Dict[str, Any]) -> List[Transaction]:

        skiprows = self._get_skiprows(read_file_lines(filepath), config.get('header', ''))
        sep = config.get('sep', ';')  # Use config or default ;     
        df = pd.read_csv(filepath, sep=sep, skiprows=skiprows, encoding=config.get('encoding', 'latin1'), dtype=str, on_bad_lines='skip')
        df.columns = df.columns.str.strip() # Clean column names
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

        # After description building
        print("=== DEBUG: before exclusions/filtering ===")
        print("Columns:", df.columns.tolist())
        print("Date sample:", df['date'].head().tolist())
        print("Description sample:", df['description'].head().tolist())
        print("Row count:", len(df))
        
        # Drop rows with no date or description - bad data
        df = df[df['date'].notna() & (df['description'].str.strip() != '')]
        
        # Early validation
        print("=== DEBUG: after date/description filter ===")
        print("Row count:", len(df))
        print("Any 'Saldo' in descriptions?", any('saldo' in str(d).lower() for d in df['description']))
        
        # Filter exclusions 
        df = self._apply_exclusions(df, config)

        # After exclusions
        print("=== DEBUG: after exclusions ===")
        print("Row count:", len(df))
        
        # Amount/Type
        if 'debit_col' in config:
            df[['amount', 'transactionType']] = df.apply(
                lambda row: self._parse_amount(row, config['debit_col'], config['credit_col']), axis=1, result_type='expand'
            )
            if config.get('drop_empty_amount', True):
                df = df[df['transactionType'] != TransactionType.NULL.value]

        else:  # TODO: Make more flexible -> currently assumes single-amount column is always a debit
            decimal_sep = config.get("decimal_sep", ".")
            df['amount'] = df[config['amount_col']].apply(lambda x: to_float(x, decimal_sep) if str(x).strip() else None) * -1
            df['transactionType'] = TransactionType.DEBIT.value

        # Other fields
        df['currency'] = self._resolve_currency(df, config)
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
    def _get_skiprows(lines: List[str], header) -> int:
        """Return the index of the first line containing any of the header signatures."""
        signatures = header if isinstance(header, list) else [header]

        for i, line in enumerate(lines):
            if any(sig in line for sig in signatures):
                return i

        expected = ", ".join(signatures)
        raise ValueError(f"Header not found. Expected one of: {expected}")


    def _parse_amount(self, row: pd.Series, debit_col: str, credit_col: str) -> tuple:
        decimal_sep = self.config.get("decimal_sep", ".")

        debit_raw = row.get(debit_col, '').strip()
        credit_raw = row.get(credit_col, '').strip()

        if debit_raw:
            amount = abs(to_float(debit_raw, decimal_sep)) * -1
            return amount, TransactionType.DEBIT.value

        if credit_raw:
            amount = abs(to_float(credit_raw, decimal_sep))
            return amount, TransactionType.CREDIT.value

        return 0.0, TransactionType.NULL.value


    @staticmethod
    def _generate_id(date, desc: str, amt: float) -> str:
        date_str = date.strftime('%Y%m%d') if pd.notna(date) else 'unknown'
        key = f"{date_str}-{str(desc)[:50]}-{amt}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    @staticmethod
    def _apply_exclusions(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Exclude transactions whose descriptions match configured literal patterns."""
        exclude_patterns = config.get('exclude_patterns', [])
        if not exclude_patterns:
            return df

        escaped_patterns = [re.escape(pattern) for pattern in exclude_patterns]
        pattern = '|'.join(escaped_patterns)

        is_excluded = df['description'].str.contains(pattern, case=False, na=False, regex=True)
        dropped = is_excluded.sum()
        df = df[~is_excluded]
        print(f"Excluded {dropped} rows matching exclusion patterns")
        return df


    @staticmethod
    def _resolve_currency(df: pd.DataFrame, config: Dict[str, Any]) -> pd.Series:
        currency_col = config.get('currency_col')
        fixed_currency = config.get('fixed_currency')

        if currency_col and currency_col in df.columns:
            return df[currency_col].str.strip()
        if fixed_currency:
            return pd.Series(fixed_currency, index=df.index)
        raise ValueError("Config must define either 'currency_col' or 'fixed_currency'")
    
    @staticmethod
    def _clean_config_value(value):
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return [v.strip() if isinstance(v, str) else v for v in value]
        return value

