"""Pixel positions for default-width and individually resized table columns."""

from bisect import bisect_right


class ColumnLayout:
    def __init__(self, default_width, minimum_width=48):
        self.default_width = default_width
        self.minimum_width = minimum_width
        self.widths = {}
        self._edges = [0]

    def width(self, index):
        return self.widths.get(index, self.default_width)

    def edge(self, index):
        while len(self._edges) <= index:
            column = len(self._edges) - 1
            self._edges.append(self._edges[-1] + self.width(column))
        return self._edges[index]

    def set_width(self, index, width):
        width = max(self.minimum_width, int(width))
        if self.width(index) == width:
            return False
        if width == self.default_width:
            self.widths.pop(index, None)
        else:
            self.widths[index] = width
        del self._edges[index + 1:]
        return True

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
