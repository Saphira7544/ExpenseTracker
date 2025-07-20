

def read_file_lines(file_path: str, encoding: str = "utf-8") -> list[str]:
    with open(file_path, encoding=encoding) as f:
        return f.readlines()