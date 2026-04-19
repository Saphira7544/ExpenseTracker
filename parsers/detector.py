from typing import Dict, Any
from parsers.bank_configs import ALL_BANK_CONFIGS
from utils.file_utils import read_file_lines


def detect_config(filepath: str) -> Dict[str, Any]:
    lines = read_file_lines(filepath)

    for bank_name, bank_data in ALL_BANK_CONFIGS.items():
        bank_patterns = bank_data.get("_bank_exclude_patterns", [])
        for subtype, config in bank_data.items():
            if subtype.startswith("_"):
                continue
            if config.get("header") and any(config["header"] in line for line in lines[:20]):
                return {**config, "exclude_patterns": bank_patterns}

    raise ValueError(f"Could not detect file format for: {filepath}")
