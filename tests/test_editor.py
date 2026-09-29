import tempfile
import unittest
import os
import stat
from pathlib import Path

from python_to_exe.editor.document import EditorDocument


class EditorDocumentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tas editor test ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.document = EditorDocument()

    def test_tsv_round_trip_keeps_tabs_utf8_and_mixed_newlines(self):
        path = self.folder / "日本語 sample.tsv"
        original = "1\ta\r\n// 日本語\n2\tls(90)\r"
        path.write_bytes(original.encode("utf-8"))
        self.document.open(path)
        self.assertEqual(self.document.text, "1\ta\n// 日本語\n2\tls(90)\n")
        self.assertFalse(self.document.modified)
        self.document.save()
        self.assertEqual(path.read_bytes(), original.encode("utf-8"))
        self.document.set_text(self.document.text.replace("a", "b", 1))
        self.assertTrue(self.document.modified)
        self.document.save()
        self.assertEqual(path.read_bytes(), original.replace("a", "b", 1).encode("utf-8"))
        self.assertFalse(self.document.modified)

    def test_txt_save_as_and_modified_state(self):
        self.document.set_text("0\tKEY_A\t日本語\n")
        self.assertTrue(self.document.modified)
        first = self.folder / "input.txt"
        self.assertEqual(self.document.save(first), first)
        self.assertEqual(first.read_bytes(), "0\tKEY_A\t日本語\n".encode("utf-8"))
        self.assertFalse(self.document.modified)
        second = self.folder / "copy.tsv"
        self.document.save(second)
        self.assertEqual(self.document.path, second)
        self.assertEqual(second.read_bytes(), first.read_bytes())
        self.document.set_text("changed")
        self.assertTrue(self.document.modified)
        self.document.set_text("0\tKEY_A\t日本語\n")
        self.assertFalse(self.document.modified)

    def test_new_lines_keep_existing_crlf_style(self):
        path = self.folder / "windows.tsv"
        path.write_bytes(b"1\ta\r\n")
        self.document.open(path)
        self.document.set_text("1\ta\n2\tb\n")
        self.document.save()
        self.assertEqual(path.read_bytes(), b"1\ta\r\n2\tb\r\n")

    def test_row_insert_delete_keeps_mixed_endings_with_original_rows(self):
        path = self.folder / "mixed.tsv"
        original = b"a\r\nb\nc\r\n"
        path.write_bytes(original)
        self.document.open(path)
        self.document.set_text("a\n\nb\nc\n")
        self.document.save()
        self.assertEqual(path.read_bytes(), b"a\r\n\r\nb\nc\r\n")
        self.document.set_text("a\nb\nc\n")
        self.document.save()
        self.assertEqual(path.read_bytes(), original)

    @unittest.skipUnless(os.name == "posix", "POSIX file modes only")
    def test_save_preserves_existing_file_mode(self):
        path = self.folder / "mode.tsv"
        path.write_text("1\ta")
        path.chmod(0o644)
        self.document.open(path)
        self.document.set_text("1\tb")
        self.document.save()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_empty_file_and_new_document(self):
        path = self.folder / "empty.tsv"
        path.write_bytes(b"")
        self.document.open(path)
        self.assertEqual(self.document.text, "")
        self.document.save()
        self.assertEqual(path.read_bytes(), b"")
        self.document.set_text("1\ta")
        self.document.new()
        self.assertIsNone(self.document.path)
        self.assertEqual(self.document.text, "")
        self.assertFalse(self.document.modified)

    def test_invalid_path_and_decode_failure_keep_current_document(self):
        good = self.folder / "good.tsv"
        good.write_text("1\ta")
        self.document.open(good)
        for bad in (self.folder / "missing.tsv", self.folder / "wrong.csv"):
            with self.assertRaises((OSError, ValueError)):
                self.document.open(bad)
            self.assertEqual(self.document.path, good)
            self.assertEqual(self.document.text, "1\ta")
        invalid = self.folder / "invalid.txt"
        invalid.write_bytes(b"\xff")
        with self.assertRaises(UnicodeError):
            self.document.open(invalid)
        self.assertEqual(self.document.path, good)
        with self.assertRaises(ValueError):
            self.document.save(self.folder / "wrong.csv")
        self.assertEqual(self.document.path, good)

    def test_failed_save_keeps_original_contents_and_modified_state(self):
        path = self.folder / "good.tsv"
        path.write_text("1\ta")
        self.document.open(path)
        self.document.set_text("1\tb")
        with self.assertRaises(OSError):
            self.document.save(self.folder / "missing folder" / "next.tsv")
        self.assertEqual(path.read_text(), "1\ta")
        self.assertEqual(self.document.path, path)
        self.assertTrue(self.document.modified)


if __name__ == "__main__":
    unittest.main()
