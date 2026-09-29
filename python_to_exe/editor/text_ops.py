"""Small raw-text operations shared by search UI and headless tests."""


def find_next(text, query, start=0):
    if not query:
        return None
    start = max(0, min(start, len(text)))
    position = text.find(query, start)
    if position < 0:
        position = text.find(query)
    return (position, position + len(query)) if position >= 0 else None


def find_previous(text, query, start=None):
    if not query:
        return None
    start = len(text) if start is None else max(0, min(start, len(text)))
    position = text.rfind(query, 0, start)
    if position < 0:
        position = text.rfind(query)
    return (position, position + len(query)) if position >= 0 else None


def replace_current(text, query, replacement, selection):
    if not query or selection is None:
        return None
    start, end = selection
    if start < 0 or end > len(text) or text[start:end] != query:
        return None
    return text[:start] + replacement + text[end:]


def replace_all(text, query, replacement):
    if not query:
        return text, 0
    return text.replace(query, replacement), text.count(query)


def line_column(index):
    """Convert a Tk Text index to one-based line and column numbers."""
    line, column = index.split(".")
    return int(line), int(column) + 1


def file_kind(path):
    return "nx-TAS" if path is not None and path.suffix.lower() == ".txt" else "TSV-TAS"
