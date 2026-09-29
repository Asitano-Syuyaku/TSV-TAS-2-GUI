"""Literal tab-separated rows for the table view; no TSV-TAS interpretation."""


class CellSelection:
    """Anchor and active cell define one rectangular selection."""

    def __init__(self, anchor=(0, 0), active=None):
        self.anchor = anchor
        self.active = active if active is not None else anchor

    @property
    def bounds(self):
        return (min(self.anchor[0], self.active[0]),
                max(self.anchor[0], self.active[0]),
                min(self.anchor[1], self.active[1]),
                max(self.anchor[1], self.active[1]))

    def move_to(self, row, column, extend=False):
        if not extend:
            self.anchor = row, column
        self.active = row, column

    def clamp(self, row_count, column_count):
        def inside(cell):
            return min(cell[0], row_count - 1), min(cell[1], column_count)
        self.anchor = inside(self.anchor)
        self.active = inside(self.active)


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

    def copy(self):
        duplicate = object.__new__(TableModel)
        duplicate.rows = [cells.copy() for cells in self.rows]
        duplicate.column_count = self.column_count
        return duplicate

    def _recount(self):
        self.column_count = max(map(len, self.rows))

    def copy_range(self, bounds):
        top, bottom, left, right = bounds
        return "\n".join("\t".join(self.cell(row, column)
                                for column in range(left, right + 1))
                         for row in range(top, bottom + 1))

    def clear_range(self, bounds):
        top, bottom, left, right = bounds
        for row in range(top, bottom + 1):
            cells = self.rows[row]
            for column in range(left, min(right + 1, len(cells))):
                cells[column] = ""

    @staticmethod
    def clipboard_rows(text):
        # Spreadsheet clipboards commonly include one terminal row separator.
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if len(lines) > 1 and lines[-1] == "":
            lines.pop()
        return [line.split("\t") for line in lines]

    def paste(self, row, column, text):
        block = self.clipboard_rows(text)
        for offset, values in enumerate(block):
            target = row + offset
            while target >= self.row_count:
                self.rows.append([""])
            cells = self.rows[target]
            width = column + len(values)
            if len(cells) < width:
                cells.extend([""] * (width - len(cells)))
            cells[column:width] = values
        self._recount()
        return len(block), max(map(len, block))

    def insert_row(self, row):
        self.rows.insert(row, [""])
        self._recount()

    def delete_row(self, row):
        if self.row_count == 1:
            self.rows[0] = [""]
        else:
            self.rows.pop(row)
        self._recount()

    def duplicate_row(self, row):
        self.rows.insert(row + 1, self.rows[row].copy())
        self._recount()

    def insert_column(self, column):
        for cells in self.rows:
            if column > len(cells):
                cells.extend([""] * (column - len(cells)))
            cells.insert(column, "")
        self._recount()

    def delete_column(self, column):
        for cells in self.rows:
            if column < len(cells):
                cells.pop(column)
            if not cells:
                cells.append("")
        self._recount()

    def to_text(self):
        return "\n".join("\t".join(cells) for cells in self.rows)


def visible_span(origin, viewport, prefix, size, count):
    """Bound a canvas draw pass to visible row/column indexes plus one margin."""
    if viewport <= 0 or count <= 0:
        return range(0)
    first = max(0, int((origin - prefix) // size))
    last = min(count, int((origin + viewport - prefix) // size) + 2)
    return range(min(first, count), max(min(first, count), last))
