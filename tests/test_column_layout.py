"""Variable column geometry without a Tk display."""

import unittest

from python_to_exe.editor.column_layout import ColumnLayout


class ColumnLayoutTests(unittest.TestCase):
    def test_positions_hits_and_virtual_columns_after_resize(self):
        columns = ColumnLayout(160)
        self.assertEqual(columns.cover_count(470), 3)
        self.assertEqual(columns.resize_hit(160, 10), 0)
        self.assertIsNone(columns.resize_hit(140, 10))
        self.assertTrue(columns.set_width(0, 220))
        self.assertEqual([columns.edge(index) for index in range(5)],
                         [0, 220, 380, 540, 700])
        self.assertEqual(columns.width(1), 160)
        self.assertEqual(columns.width(100), 160)
        self.assertEqual(columns.at(219, 10), 0)
        self.assertEqual(columns.at(220, 10), 1)
        self.assertEqual(columns.resize_hit(220, 10), 0)
        self.assertEqual(columns.resize_hit(380, 10), 1)
        self.assertIn(2, columns.visible(360, 300, 48, 10))

    def test_minimum_width_and_cached_edge_invalidation(self):
        columns = ColumnLayout(160, minimum_width=48)
        self.assertEqual(columns.edge(4), 640)
        self.assertTrue(columns.set_width(1, -100))
        self.assertEqual(columns.width(1), 48)
        self.assertEqual(columns.edge(4), 528)
        self.assertFalse(columns.set_width(1, 20))
        self.assertTrue(columns.set_width(1, 160))
        self.assertEqual(columns.edge(4), 640)
        self.assertEqual(columns.widths, {})


if __name__ == "__main__":
    unittest.main()
