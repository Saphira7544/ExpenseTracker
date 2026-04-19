from typing import List

def read_file_lines(file_path: str, encoding: str = "latin1") -> List[str]:
    with open(file_path, encoding=encoding, errors='replace') as f:
        return f.readlines()