from typing import Dict, Any, Iterable
from parsers.bank_configs import ALL_BANK_CONFIGS
from utils.file_utils import read_file_lines


def default_formats() -> list[Dict[str, Any]]:
    """The built-in formats from bank_configs.py (used to seed each user's Banks page)."""
    return [
        dict(config)
        for bank_data in ALL_BANK_CONFIGS.values()
        for subtype, config in bank_data.items()
        if not subtype.startswith("_")
    ]


def detect_config(filepath: str, formats: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Return the first format whose header signatures all appear near the top of the file."""
    formats = default_formats() if formats is None else list(formats)
    lines_by_encoding: dict[str, list[str]] = {}

    for config in formats:
        encoding = config.get("encoding") or "latin1"
        if encoding not in lines_by_encoding:
            lines_by_encoding[encoding] = read_file_lines(filepath, encoding)
        if _matches_header(config.get("header", []), lines_by_encoding[encoding]):
            return dict(config)

    raise ValueError(f"Could not detect file format for: {filepath}")


def _matches_header(header_signatures: list, lines: list) -> bool:
    """All signatures must be present in the first 20 lines."""
    first_20 = lines[:20]
    signatures = [s.strip() for s in header_signatures if s and s.strip()]
    return bool(signatures) and all(
        any(signature in line for line in first_20)
        for signature in signatures
    )
