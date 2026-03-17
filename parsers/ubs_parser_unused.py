import pandas as pd
import os
from typing import List
from models.transaction import Transaction, TransactionType
from .base_parser import BaseParser
from utils.file_utils import read_file_lines


class UBSParser(BaseParser):

    DEBIT_HEADER = "Trade date"
    PREPAID_HEADER = "Account number"

    def parse(self, file_path: str) -> List[Transaction]:
        lines = read_file_lines(file_path)

        # Trade date --> UBS Debit Account
        if any(self.DEBIT_HEADER in line for line in lines):
            return self._parse_file(
                file_path,
                skiprows=self._get_header_index(lines, self.DEBIT_HEADER),
                date_col="Value date",
                desc_cols=["Description1", "Description2", "Description3"],
                account_name="UBS Debit",
                id_col="Transaction no.",
            )
        # Account number --> UBS Prepaid Card
        elif any(self.PREPAID_HEADER in line for line in lines):
            return self._parse_file(
                file_path,
                skiprows=self._get_header_index(lines, self.PREPAID_HEADER),
                date_col="Purchase date",
                desc_cols=["Booking text"],
                account_name="UBS Prepaid",
                id_col=None,  # will generate a composite ID
            )
        else:
            raise ValueError(f"Unknown UBS file format: {file_path}")

    def _get_header_index(self, lines: list, header_name: str) -> int:
        return next(i for i, line in enumerate(lines) if header_name in line)

    def _parse_file(
        self,
        file_path: str,
        skiprows: int,
        date_col: str,
        desc_cols: list,
        account_name: str,
        id_col: str = None,
    ) -> List[Transaction]:
        df = pd.read_csv(file_path, sep=";", skiprows=skiprows, encoding="utf-8", dtype=str)
        df = df.fillna("")

        # Drop empty rows for debit files
        if self.DEBIT_HEADER in df.columns:
            df = df.dropna(subset=[self.DEBIT_HEADER, desc_cols[0]], how="all")

        # Amount and transaction type
        df[["amount", "transactionType"]] = df.apply(lambda row: pd.Series(self._parse_amount(row)), axis=1)

        # Date
        df["date"] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")  # dayfirst=True works for both formats

        # Description
        # Aggregate if multiple descriptions
        df["description"] = df[desc_cols].agg(" ".join, axis=1).str.strip() if len(desc_cols) > 1 else df[desc_cols[0]].str.strip()

        df["account"] = account_name
        df["sourceFile"] = os.path.basename(file_path)

        # Currency 
        df["currency"] = df["Currency"].str.strip()

        # Transaction ID
        if id_col and id_col in df.columns:
            df["transactionId"] = df[id_col].str.strip()
        else:
            # For prepaid, generate composite ID
            df["transactionId"] = (
                df.get(self.PREPAID_HEADER, "").astype(str).str.strip()
                + "-" + df[date_col].astype(str).str.strip()
                + "-" + df[desc_cols[0]].astype(str).str.strip()
            )

        return [
            Transaction(
                transactionId=row.transactionId,
                transactionType=row.transactionType,
                date=row.date,
                description=row.description,
                amount=row.amount,
                currency=row.currency,
                account=row.account,
                sourceFile=row.sourceFile,
                category=""
            )
            for row in df.itertuples()
        ]

    @staticmethod
    def _parse_amount(row):
        debit = str(row.get("Debit", "")).strip()
        credit = str(row.get("Credit", "")).strip()
        if debit:
            return float(debit), TransactionType.DEBIT
        elif credit:
            return float(credit), TransactionType.CREDIT
        return 0.0, TransactionType.NULL
