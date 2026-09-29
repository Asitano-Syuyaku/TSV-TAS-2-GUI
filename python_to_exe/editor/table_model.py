"""Literal tab-separated rows for the table view; no TSV-TAS interpretation."""


class TableModel:
    def __init__(self, text):
        # split preserves blank rows and trailing empty cells, including a final TAB.
        self.rows = [line.split("\t") for line in text.split("\n")]
        self.column_count = max(map(len, self.rows))

    @property
    def row_count(self):
        return len(self.rows)

    def cell(self, row, column):
        cells = self.rows[row]
        return cells[column] if column < len(cells) else ""

    def line(self, row):
        return "\t".join(self.rows[row])

    def changed_line(self, row, column, value):
        if "\t" in value or "\n" in value or "\r" in value:
            raise ValueError("A cell cannot contain a tab or newline")
        cells = self.rows[row].copy()
        if column >= len(cells):
            if not value:
                return self.line(row)
            cells.extend([""] * (column + 1 - len(cells)))
        cells[column] = value
        return "\t".join(cells)

    def update_line(self, row, line):
        self.rows[row] = line.split("\t")
        self.column_count = max(self.column_count, len(self.rows[row]))

    def to_text(self):
        return "\n".join("\t".join(cells) for cells in self.rows)


def visible_span(origin, viewport, prefix, size, count):
    """Bound a canvas draw pass to visible row/column indexes plus one margin."""
    if viewport <= 0 or count <= 0:
        return range(0)
    first = max(0, int((origin - prefix) // size))
    last = min(count, int((origin + viewport - prefix) // size) + 2)
    return range(min(first, count), max(min(first, count), last))
