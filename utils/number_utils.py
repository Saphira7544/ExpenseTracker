

def to_float(value: str, decimal_sep: str = ".") -> float:
    if value is None:
        raise ValueError("Amount value is None")

    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError("Amount value is empty")

    # Drop thousands separators: 1'234.50 / 1,234.50 / 1 234.50, or 1.234,50 for ","
    cleaned = cleaned.replace("'", "").replace("’", "").replace(" ", "").replace(" ", "")
    if decimal_sep == ",":
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")

    return float(cleaned)
