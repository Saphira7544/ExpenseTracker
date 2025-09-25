import pandas as pd
from datetime import datetime
import os
import math
from typing import List
from models.transaction import Transaction
from models.transaction import TransactionType
from .base_parser import BaseParser
from utils.file_utils import read_file_lines


class UBSParser(BaseParser):
    def parse(self, file_path: str) -> List[Transaction]:
        lines = read_file_lines(file_path)
        header_index = next(i for i, line in enumerate(lines) if "Trade date" in line)

        df = pd.read_csv(
            file_path,
            sep=";",
            skiprows=header_index,
            encoding="utf-8",
            dtype=str
        )

        df = df.dropna(subset=["Trade date", "Description1"], how="all")

        def parse_amount_and_type(row):
            debit = row.get("Debit", "")
            credit = row.get("Credit", "")

            # Normalize in case value empty -> NaN
            debit = "" if pd.isna(debit) else str(debit).strip()
            credit = "" if pd.isna(credit) else str(credit).strip()

            if debit:
                return float(debit), TransactionType.DEBIT
            elif credit:
                return float(credit), TransactionType.CREDIT
            return 0.0, TransactionType.NULL
        
        df[["amount", "transactionType"]] = df.apply(
                lambda row: pd.Series(parse_amount_and_type(row)), axis=1
            )        
        df["date"] = pd.to_datetime(df["Value date"], format="%Y-%m-%d", errors="coerce")
        df["currency"] = df["Currency"].fillna("CHF")
        df["description"] = df[["Description1", "Description2", "Description3"]].fillna("").agg(" ".join, axis=1).str.strip()
        df["account"] = "UBS"
        df["sourceFile"] = os.path.basename(file_path)
        df["transactionId"] = df["Transaction no."].str.strip()


        return [
            Transaction(
                transactionId=row.transactionId,
                transactionType=row.transactionType,
                date=row.date,
                description=row.description,
                amount=row.amount,
                currency=row.currency,
                account=row.account,
                sourceFile=row.sourceFile               
            ) 
            for row in df.itertuples()
        ]
