"""Pixel positions for default-width and individually resized table columns."""

from bisect import bisect_right


MIN_COLUMN_WIDTH = 48
MAX_COLUMN_WIDTH = 2000


def clean_column_widths(values):
    """Validate sparse JSON preferences without allocating column geometry."""
    cleaned = {}
    if not isinstance(values, dict):
        return cleaned
    for key, width in values.items():
        if type(key) not in (str, int) or type(width) is not int:
            continue
        try:
            index = int(key)
        except ValueError:
            continue
        if index >= 0 and MIN_COLUMN_WIDTH <= width <= MAX_COLUMN_WIDTH:
            cleaned[str(index)] = width
    return cleaned


class ColumnLayout:
    def __init__(self, default_width, minimum_width=MIN_COLUMN_WIDTH, default_widths=None):
        self.default_width = default_width
        self.minimum_width = minimum_width
        self.default_widths = dict(default_widths or {})
        self.widths = {}
        self._edges = [0]

    def default_for(self, index):
        return self.default_widths.get(index, self.default_width)

    def width(self, index):
        return self.widths.get(index, self.default_for(index))

    def edge(self, index):
        while len(self._edges) <= index:
            column = len(self._edges) - 1
            self._edges.append(self._edges[-1] + self.width(column))
        return self._edges[index]

    def set_width(self, index, width):
        width = max(self.minimum_width, min(MAX_COLUMN_WIDTH, int(width)))
        if self.width(index) == width:
            return False
        if width == self.default_for(index):
            self.widths.pop(index, None)
        else:
            self.widths[index] = width
        del self._edges[index + 1:]
        return True

    def export_widths(self):
        """Only user overrides; suggested/default widths need no persistence."""
        return {str(index): width for index, width in self.widths.items()}

    def import_widths(self, values):
        self.widths.clear()
        self._edges = [0]
        for key, width in clean_column_widths(values).items():
            self.set_width(int(key), width)

    def cover_count(self, pixels):
        while self._edges[-1] < pixels:
            column = len(self._edges) - 1
            self._edges.append(self._edges[-1] + self.width(column))
        return max(1, len(self._edges) - 1)

    def at(self, pixels, count):
        if count <= 0:
            return 0
        self.edge(count)
        return min(count - 1, max(0, bisect_right(self._edges, pixels) - 1))

    def visible(self, origin, viewport, gutter, count):
        if viewport <= 0 or count <= 0:
            return range(0)
        first = max(0, self.at(origin - gutter, count) - 1)
        last = min(count, self.at(origin + viewport - gutter, count) + 2)
        return range(first, max(first, last))

    def resize_hit(self, pixels, count, tolerance=5):
        """Return the column whose right edge is near a header pointer."""
        if count <= 0:
            return None
        column = self.at(pixels, count)
        if column and abs(pixels - self.edge(column)) <= tolerance:
            return column - 1
        if abs(pixels - self.edge(column + 1)) <= tolerance:
            return column
        return None
