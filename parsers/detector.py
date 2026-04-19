from typing import Dict, Any
from parsers.bank_configs import ALL_BANK_CONFIGS
from utils.file_utils import read_file_lines

def detect_config(filepath: str) -> Dict[str, Any]:
    lines = read_file_lines(filepath)

    for config in ALL_BANK_CONFIGS:
        header = config.get("header")
        if header and any(header in line for line in lines[:20]):
            return config

    raise ValueError(f"Could not detect file format for: {filepath}")
