"""Non-destructive converter snapshots, including the actual Tk/worker boundary."""

import subprocess
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.editor.line_positions import analyze_positions
from python_to_exe.editor.snapshot import ScriptSnapshot, script_workspace
from python_to_exe.editor.validation import analyze_script, validate_script
from python_to_exe.editor.window import EditorWindow


ROOT = Path(__file__).resolve().parents[1]


class SnapshotTests(unittest.TestCase):
    def test_workspace_preserves_utf8_tabs_and_newlines_and_cleans_on_error(self):
        snapshot = ScriptSnapshot("// 日本語\r\n1\ta\t\n\t\r\n")
        with script_workspace(snapshot) as (source, destination):
            self.assertEqual(source.suffix, ".tsv")
            self.assertEqual(source.read_bytes(), snapshot.text.encode("utf-8"))
            self.assertEqual(source.parent, destination)
            # The writer is closed, permitting Windows replacement/deletion too.
            source.rename(destination / "renamed.tsv")
        self.assertFalse(destination.exists())
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with script_workspace(ScriptSnapshot("", ".txt")) as (source, destination):
                self.assertEqual(source.read_bytes(), b"")
                raise RuntimeError("test failure")
        self.assertFalse(destination.exists())
        with self.assertRaisesRegex(ValueError, "Snapshot must"):
            with script_workspace(ScriptSnapshot("", ".csv")):
                self.fail("unsupported snapshot extension")

    def recording_runner(self, snapshot, calls):
        def run(command, **options):
            source, output = map(Path, command[-2:])
            calls.append((command, source.parent))
            self.assertEqual(source.read_bytes(), snapshot.text.encode("utf-8"))
            self.assertEqual(source.parent, output.parent)
            self.assertEqual(options["env"]["PYTHONUTF8"], "1")
            self.assertEqual(options["encoding"], "utf-8")
            return subprocess.run(command, **options)
        return run

    def test_validate_analyze_and_positions_share_isolated_workspace_and_flags(self):
        text = "$angle = 90\n2\tls($angle)\ta\n1\tb"
        snapshot = ScriptSnapshot(text)
        for operation in ("validate", "analyze", "positions"):
            for output_format in (("binary", "stas", "nxtas") if operation != "positions"
                                  else ("binary",)):
                with self.subTest(operation=operation, output_format=output_format):
                    calls = []
                    options = dict(base_dir=ROOT, runner=self.recording_runner(snapshot, calls))
                    if operation == "positions":
                        result = analyze_positions(text, **options)
                        self.assertEqual(result.positions.total_frames, 3)
                    else:
                        function = validate_script if operation == "validate" else analyze_script
                        result = function(snapshot, output_format,
                                          skip_empty=output_format == "nxtas", **options)
                        self.assertTrue(result.success, result)
                        if operation == "analyze":
                            self.assertEqual(result.frames.total_frames, 3)
                    self.assertEqual(len(calls), 1)
                    command, directory = calls[0]
                    flags = "".join(arg[1:] for arg in command[2:-2] if arg.startswith("-"))
                    self.assertNotIn("f", flags)
                    self.assertEqual("d" in flags, operation == "analyze")
                    self.assertEqual("m" in flags, operation == "positions")
                    self.assertFalse(directory.exists())

    def test_snapshot_error_source_lines_match_and_cleanup_on_failure_or_missing_csv(self):
        snapshot = ScriptSnapshot("// 日本語\n1\tls(")
        for function in (validate_script, analyze_script):
            calls = []
            result = function(snapshot, "binary", base_dir=ROOT,
                              runner=self.recording_runner(snapshot, calls))
            report = result if function == validate_script else result.report
            self.assertFalse(result.success)
            self.assertIn("Syntax error(s) on line 2", report.stderr)
            self.assertEqual(report.problems(2)[0].line, 2)
            self.assertFalse(calls[0][1].exists())
        directories = []

        def missing_csv(command, **options):
            directories.append(Path(command[-1]).parent)
            return subprocess.CompletedProcess(command, 0, "", "")

        result = analyze_script(ScriptSnapshot("1\ta"), "binary", base_dir=ROOT,
                                runner=missing_csv)
        self.assertFalse(result.success)
        self.assertIn("Debug CSV was not generated", result.report.stderr)
        self.assertFalse(directories[0].exists())

    def test_txt_snapshot_keeps_nx_pipeline_and_has_no_guessed_source_jump(self):
        snapshot = ScriptSnapshot("0 KEY_A 0;0 0;0\n1 KEY_B 0;0 0;0\n", ".txt")
        for function in (validate_script, analyze_script):
            calls = []

            def run(command, **options):
                source, output = map(Path, command[-2:])
                calls.append(command)
                self.assertEqual(source.parent, output.parent)
                if len(calls) == 1:
                    self.assertEqual(source.suffix, ".txt")
                    self.assertEqual(source.read_bytes(), snapshot.text.encode("utf-8"))
                return subprocess.run(command, **options)

            result = function(snapshot, "binary", base_dir=ROOT, runner=run)
            self.assertTrue(result.success, result)
            report = result if function == validate_script else result.report
            self.assertFalse(report.source_is_tsv)
            self.assertEqual(Path(calls[0][1]).name, "nx-tas-to-tsv-tas.py")
            self.assertEqual(Path(calls[1][1]).name, "tsv-tas.py")
            self.assertFalse(Path(calls[0][-2]).parent.exists())


class SnapshotTkTests(unittest.TestCase):
    def app_and_editor(self, language="en", path=None):
        try:
            app = TASConverterApp(language)
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.addCleanup(app.destroy)
        if path is not None:
            app._set_input_path(path)
        app.ftp_var.set(True)
        app.debug_var.set(True)
        app.open_editor()
        editor = next(child for child in app.winfo_children() if isinstance(child, EditorWindow))
        app.update()
        return app, editor

    def wait_for(self, app, condition):
        deadline = time.monotonic() + 8
        while not condition() and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        app.update()
        self.assertTrue(condition(), "background operation did not finish")

    @staticmethod
    def settings(app):
        return tuple(widget.get() for widget in (app.input_entry, app.output_entry,
                     app.outname_entry, app.ip_entry, app.port_entry, app.user_entry,
                     app.pass_entry, app.format_var, app.skip_var, app.debug_var, app.ftp_var))

    @staticmethod
    def shortcut(widget, keysym):
        # Exercise the registered Tk key callback without compositor focus races
        # between the many root windows created by the integration suite.
        script = widget.bind(f"<{keysym}>")
        command = script.split("[", 1)[1].split(" ", 1)[0]
        return widget.tk.call(command, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "", 0,
                              keysym, 0, str(widget), 2, 0, 0, 0)

    def test_modified_table_snapshot_keeps_disk_settings_selection_and_undo(self):
        with tempfile.TemporaryDirectory(prefix="tas snapshot 日本語 ") as folder:
            source = Path(folder) / "script with spaces.tsv"
            original = b"1\ta\r\n1\tb\n"
            source.write_bytes(original)
            app, editor = self.app_and_editor(path=source)
            settings = self.settings(app)
            editor.show_table()
            grid = editor.table_grid
            grid.selected = (1, 1)
            grid.begin_edit(initial="ls(")
            before = grid.selection.anchor, grid.selection.active
            with patch("python_to_exe.editor.window.filedialog.asksaveasfilename",
                       side_effect=AssertionError("Validate/Analyze must not ask to save")):
                self.assertTrue(editor.validate())  # Commits the pending cell first.
                self.wait_for(app, lambda: not editor._validation_pending)
                self.assertEqual(editor.document.text, "1\ta\n1\tls(\n")
                self.assertTrue(editor.document.modified)
                self.assertEqual(editor.document.path, source)
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual((grid.selection.anchor, grid.selection.active), before)
                self.assertEqual(editor._problem_rows.get(1), 2)
                editor._problem_double_click(type("Event", (), {"x": 3, "y": 3})())
                self.assertEqual(grid.selected, (1, 0))
                editor.show_raw()
                editor._problem_double_click(type("Event", (), {"x": 3, "y": 3})())
                self.assertEqual(editor.text.index("insert"), "2.0")
                editor.undo()
                self.assertEqual(editor.document.text, "1\ta\n1\tb\n")
                self.assertFalse(editor.document.modified)
                editor.redo()
                self.assertEqual(editor.document.text, "1\ta\n1\tls(\n")
                editor.undo()
                editor.show_table()
                grid.selected = (0, 0)
                grid.begin_edit(initial="3")
                self.assertTrue(editor.analyze_frames())
                self.wait_for(app, lambda: not editor._analysis_pending)
                self.assertEqual(editor._frame_inspector.frames.total_frames, 4)
                self.assertIn(source.name, editor._frame_inspector.title())
                self.assertTrue(editor.document.modified)
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(self.settings(app), settings)
                editor.undo()
                self.assertFalse(editor.document.modified)
                editor.redo()
                self.assertEqual(editor.document.text, "3\ta\n1\tb\n")
            # F5 remains an explicit save, unlike the two inspection operations.
            converted = []
            editor.on_convert = lambda path: converted.append(path.read_bytes()) or True
            self.assertTrue(editor.save_and_convert())
            self.assertEqual(converted, [b"3\ta\r\n1\tb\n"])
            self.assertFalse(editor.document.modified)

    def test_untitled_f6_f7_use_current_buffer_and_localized_display_name(self):
        for language in ("en", "ja"):
            with self.subTest(language=language):
                app, editor = self.app_and_editor(language)
                snapshot = "$angle = 90\n2\tls($angle)"
                editor.text.insert("1.0", snapshot)
                editor.text.edit_separator()
                editor.text.focus_force()
                app.update()
                with patch("python_to_exe.editor.window.filedialog.asksaveasfilename",
                           side_effect=AssertionError("untitled checks must not Save As")):
                    self.assertEqual(self.shortcut(editor.text, "F6"), "break")
                    self.assertTrue(editor._validation_pending)
                    self.wait_for(app, lambda: not editor._validation_pending)
                    self.assertEqual(editor._problems_title.cget("text"), editor.words["no_errors"])
                    with patch.object(editor, "on_analyze", wraps=editor.on_analyze) as request:
                        self.assertEqual(self.shortcut(editor.text, "F7"), "break")
                        self.assertEqual(request.call_count, 1)
                    self.wait_for(app, lambda: not editor._analysis_pending)
                    self.assertEqual(editor._frame_inspector.frames.total_frames, 2)
                    self.assertEqual(editor._frame_inspector.source.name, editor.words["untitled"])
                    self.assertNotIn("snapshot.tsv", editor._frame_inspector.title())
                self.assertIsNone(editor.document.path)
                self.assertTrue(editor.document.modified)
                editor.undo()
                self.assertEqual(editor.document.text, "")
                editor.redo()
                self.assertEqual(editor.document.text, snapshot)
                self.doCleanups()

    def test_worker_results_are_stale_after_revision_changes_or_pending_cell_edits(self):
        app, editor = self.app_and_editor()
        editor.text.insert("1.0", "1\ta")
        app.update()
        self.assertTrue(editor.analyze_frames())
        self.wait_for(app, lambda: not editor._analysis_pending)
        previous = editor._frame_inspector.frames
        for name, function, pending in (("validate_script", editor.validate, "_validation_pending"),
                                         ("analyze_script", editor.analyze_frames, "_analysis_pending")):
            for change in ("revision", "pending_entry"):
                started, release = threading.Event(), threading.Event()
                original_function = validate_script if name == "validate_script" else analyze_script

                def delayed(snapshot, *args):
                    started.set()
                    release.wait(5)
                    return original_function(snapshot, *args)

                with self.subTest(operation=name, change=change), patch(
                        "python_to_exe.editor.validation." + name, delayed):
                    self.assertTrue(function())
                    self.wait_for(app, started.is_set)
                    if change == "revision":
                        # Even restoring the same text must not revive an old result.
                        editor.text.insert("end-1c", " ")
                        app.update()
                        editor.text.delete("end-2c", "end-1c")
                        app.update()
                    else:
                        editor.show_table()
                        editor.table_grid.selected = (0, 1)
                        editor.table_grid.begin_edit(initial="b")
                    release.set()
                    self.wait_for(app, lambda: not getattr(editor, pending))
                    key = "stale_validation" if name == "validate_script" else "stale_analysis"
                    self.assertEqual(editor._problems_title.cget("text"), editor.words[key])
                    self.assertEqual(editor._problem_rows, {})
                    self.assertIs(editor._frame_inspector.frames, previous)
                    if change == "pending_entry":
                        editor.table_grid.cancel_edit()
                        editor.show_raw()
                    self.assertIsNone(editor.document.path)

    def test_editor_closed_during_worker_does_not_receive_result_and_temp_is_removed(self):
        app, editor = self.app_and_editor()
        editor.text.insert("1.0", "1\ta")
        app.update()
        for method in ("validate", "analyze_frames"):
            started, release = threading.Event(), threading.Event()
            directories = []
            errors = []
            app.report_callback_exception = lambda *exception: errors.append(exception)

            def delayed(command, **options):
                directories.append(Path(command[-2]).parent)
                started.set()
                release.wait(5)
                return subprocess.run(command, **options)

            # Patch only the injected runner, not subprocess.run used inside delayed.
            from python_to_exe.editor.validation import _run_commands

            def run_commands(commands, base_dir, _runner, source_is_tsv):
                return _run_commands(commands, base_dir, delayed, source_is_tsv)

            with patch("python_to_exe.editor.validation._run_commands", run_commands):
                self.assertTrue(getattr(editor, method)())
                self.wait_for(app, started.is_set)
                editor.destroy()
                release.set()
                self.wait_for(app, lambda: not app._busy())
                self.assertTrue(editor._closed)
                self.assertFalse(directories[0].exists())
                self.assertEqual(errors, [])
            if method == "validate":
                app.open_editor()
                editor = next(child for child in app.winfo_children() if isinstance(child, EditorWindow))
                editor.text.insert("1.0", "1\ta")
