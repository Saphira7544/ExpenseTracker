

def to_float(value: str, decimal_sep: str = ".") -> float:
    if value is None:
        raise ValueError("Amount value is None")

    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError("Amount value is empty")

    if decimal_sep == ",":
        cleaned = cleaned.replace(".", "").replace(",", ".")

    return float(cleaned)
