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
            if _matches_header(config.get("header", []), lines):
                return {**config, "exclude_patterns": bank_patterns}

    raise ValueError(f"Could not detect file format for: {filepath}")


def _matches_header(header_signatures: list, lines: list) -> bool:
    """All signatures must be present in the first 20 lines."""
    first_20 = lines[:20]
    return all(
        any(signature in line for line in first_20)
        for signature in header_signatures
    )
