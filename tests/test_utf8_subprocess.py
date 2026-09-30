"""The shared child UTF-8 contract is independent of the parent's locale/env."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.converter_logic import utf8_subprocess_kwargs


class Utf8SubprocessTests(unittest.TestCase):
    def test_each_child_gets_a_fresh_environment_without_mutating_the_parent(self):
        for enabled in (None, "0"):
            with self.subTest(parent_utf8=enabled), patch.dict(os.environ):
                if enabled is None:
                    os.environ.pop("PYTHONUTF8", None)
                else:
                    os.environ["PYTHONUTF8"] = enabled
                os.environ["TAS_ENV_TEST"] = "keep"
                before = dict(os.environ)
                first, second = utf8_subprocess_kwargs(), utf8_subprocess_kwargs()
                self.assertEqual(first, {"text": True, "encoding": "utf-8", "errors": "replace",
                                         "env": {**before, "PYTHONUTF8": "1"}})
                self.assertEqual(first, second)
                self.assertIsNot(first["env"], second["env"])
                first["env"]["TAS_ENV_TEST"] = "changed in child copy"
                self.assertEqual(second["env"]["TAS_ENV_TEST"], "keep")
                self.assertEqual(dict(os.environ), before)

    def test_child_default_file_encoding_and_invalid_stream_bytes(self):
        with tempfile.TemporaryDirectory(prefix="tas UTF-8 日本語 ") as folder:
            source = Path(folder) / "入力 with spaces.tsv"
            source.write_text("// 日本語\r\n1\ta", encoding="utf-8", newline="")
            script = ("import sys; assert sys.flags.utf8_mode == 1; "
                      "f = open(sys.argv[1], newline=''); text = f.read(); f.close(); "
                      "sys.stdout.buffer.write(text.encode('utf-8') + b'\\xff'); "
                      "sys.stderr.buffer.write(b'diagnostic: \\xff')")
            # On POSIX this disables locale coercion; on Windows PYTHONUTF8=0
            # represents the same inherited opt-out. The helper must override it.
            with patch.dict(os.environ, {"PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0",
                                         "LC_ALL": "C", "LANG": "C"}):
                before = dict(os.environ)
                result = subprocess.run([sys.executable, "-c", script, str(source)],
                                        capture_output=True, **utf8_subprocess_kwargs())
                self.assertEqual(dict(os.environ), before)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "// 日本語\n1\ta\ufffd")
            self.assertEqual(result.stderr, "diagnostic: \ufffd")
