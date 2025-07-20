import pandas as pd
from datetime import datetime
import os
from typing import List
from models.transaction import Transaction
from .base_parser import BaseParser
from utils.file_utils import read_file_lines


class UBSParser(BaseParser):
    def parse(self, file_path: str) -> List[Transaction]:
        lines = read_file_lines(file_path)
        header_index = next(i for i, line in enumerate(lines) if "Trade date" in line)
