"""Resolved stick metadata and cached, read-only Palette plots."""

import subprocess
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.editor.debug_csv import (DebugFrames, SUMMARY_FIELDS, StickState,
                                           resolved_sticks)
from python_to_exe.editor.line_positions import analyze_positions
from python_to_exe.editor.stick_preview import point_position
from python_to_exe.editor.window import EditorWindow


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "1\tls(0)\trs(90)\n1\tls(90)\trs(180)\n1\tls(180)\trs(270)\n1\tls(270)\trs(0)\n"


def debug_frames(count=4, second_player=False):
    headers = SUMMARY_FIELDS + ("lx.r", "rs.r", "UnknownExtra")
    rows = []
    for frame in range(count):
        for player in ((False, True) if second_player else (False,)):
            data = {name: "0" for name in headers}
            data.update({"Frame": str(frame), "2ndPlayer": str(player),
                         "ls.x": str(frame if not player else 999), "ls.y": "32767",
                         "lx.r": "1", "ls.theta": "90", "rs.r": "0.5", "UnknownExtra": "keep"})
            rows.append(tuple(data[name] for name in headers))
    return DebugFrames(headers, tuple(rows), {}, count)


class StickDataTests(unittest.TestCase):
    def test_current_and_previous_three_frames_use_exact_1p_csv_values(self):
        samples = resolved_sticks(debug_frames(second_player=True))
        history = samples.history(3)
        self.assertEqual([row.frame for row in history], [3, 2, 1, 0])
        self.assertEqual(history[0].left, StickState(3, 32767, 1, 90))
        self.assertEqual(history[0].right.radius, 0.5)
        self.assertNotEqual(history[0].left.x, 999)  # Never substitute Cappy state.

    def test_missing_frames_and_short_history_are_not_invented(self):
        samples = resolved_sticks(debug_frames())
        self.assertEqual([row.frame for row in samples.history(0)], [0])
        self.assertEqual([row.frame for row in samples.history(1)], [1, 0])
        del samples.rows[2]
        self.assertEqual([row.frame for row in samples.history(3)], [3, 1, 0])
        self.assertEqual(samples.history(99), ())
        self.assertEqual(samples.history(-1), ())
        self.assertEqual(resolved_sticks(debug_frames(0)).history(0), ())

    def test_unavailable_numbers_and_actual_radius_header(self):
        frames = debug_frames(1)
        row = list(frames.rows[0])
        row[frames.headers.index("ls.x")] = "nan"
        row[frames.headers.index("ls.y")] = "bad"
        row[frames.headers.index("rs.r")] = "inf"
        frames = DebugFrames(frames.headers, (tuple(row),), {}, 1)
        current = resolved_sticks(frames).history(0)[0]
        self.assertIsNone(current.left.x)
        self.assertIsNone(current.left.y)
        self.assertEqual(current.left.radius, 1)  # Current converter header is lx.r.
        self.assertIsNone(current.right.radius)
        self.assertIsNone(point_position(current.left, 50, 50, 40))

    def test_plot_coordinates_scale_only_resolved_xy(self):
        self.assertEqual(point_position(StickState(32767, 0, 1, 0), 80, 70, 60), (140, 70))
        self.assertEqual(point_position(StickState(0, 32767, 1, 90), 80, 70, 60), (80, 10))

    def test_fifty_thousand_rows_are_indexed_once_and_history_does_not_scan(self):
        samples = resolved_sticks(debug_frames(50000))

        class NoScanDict(dict):
            def __iter__(self):
                raise AssertionError("Selection must not scan frame data")

        object.__setattr__(samples, "rows", NoScanDict(samples.rows))
        self.assertEqual([row.frame for row in samples.history(49999)], [49999, 49998, 49997, 49996])

    def test_one_converter_run_returns_both_metadata_and_cleans_outputs(self):
        calls, directories, binaries = [], [], []

        def runner(command, **options):
            calls.append(command)
            directories.append(Path(command[-1]).parent)
            result = subprocess.run(command, **options)
            binaries.append(Path(command[-1]).read_bytes())
            return result

        result = analyze_positions(SCRIPT, base_dir=ROOT, runner=runner, include_sticks=True)
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.positions.total_frames, 4)
        self.assertEqual(len(calls), 1)
        self.assertIn("-dm", calls[0])
        self.assertEqual(result.positions.for_line(4).start, 3)
        history = result.sticks.history(3)
        self.assertEqual([row.frame for row in history], [3, 2, 1, 0])
        self.assertEqual(history[0].left.angle, 270)
        self.assertEqual(history[0].right.angle, 0)
        self.assertFalse(any(directory.exists() for directory in directories))
        self.assertFalse(any("f" in arg[1:] for arg in calls[0][2:-2] if arg.startswith("-")))
        original = analyze_positions(SCRIPT, base_dir=ROOT, runner=runner)
        self.assertEqual(result.positions, original.positions)
        self.assertEqual(binaries[0], binaries[1])  # Debug does not change output semantics.

    def test_missing_debug_csv_preserves_valid_line_map_but_no_preview(self):
        def runner(command, **options):
            result = subprocess.run(command, **options)
            Path(command[-1] + "-debug.csv").unlink()
            return result

        result = analyze_positions(SCRIPT, base_dir=ROOT, runner=runner, include_sticks=True)
        self.assertTrue(result.success)
        self.assertEqual(result.positions.total_frames, 4)
        self.assertIsNone(result.sticks)
        self.assertIn("debug.csv", result.error)


class StickPreviewTkTests(unittest.TestCase):
    def make_editor(self, text=SCRIPT, language="en"):
        folder = tempfile.TemporaryDirectory(prefix="tas stick preview 日本語 ")
        self.addCleanup(folder.cleanup)
        work = Path(folder.name)
        source = work / "stick with spaces.tsv"
        source.write_text(text, encoding="utf-8")
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        root.withdraw()
        root._tas_app_settings = AppSettings(work / "settings.json")
        self.addCleanup(root.destroy)
        editor = EditorWindow(root, language=language, initial_path=source)
        editor.show_table()
        root.update()
        return root, editor, source

    def wait_for(self, root, condition):
        deadline = time.monotonic() + 10
        while not condition() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        root.update()
        self.assertTrue(condition(), "background analysis did not finish")

    def test_jp_en_side_by_side_preview_active_row_history_and_cached_selection(self):
        for language in ("en", "ja"):
            with self.subTest(language=language), patch(
                    "python_to_exe.editor.line_positions.analyze_positions", wraps=analyze_positions) as run:
                root, editor, source = self.make_editor(language=language)
                self.wait_for(root, lambda: editor._stick_frames is not None)
                preview, grid = editor.stick_preview, editor.table_grid
                editor.palette_canvas.yview_moveto(1)
                root.update()
                self.assertEqual(editor.input_palette.winfo_width(), 400)
                self.assertEqual(preview.status.cget("text"), "")
                self.assertFalse(preview.status.winfo_ismapped())
                self.assertEqual(preview.plots[0].winfo_y(), preview.plots[1].winfo_y())
                self.assertLessEqual(preview.plots[0].winfo_x() + preview.plots[0].winfo_width(),
                                     preview.plots[1].winfo_x())
                original = editor.document.text
                for row, frame in ((3, 3), (1, 1), (0, 0)):
                    grid.jump_to_row(row, column=1)
                    self.assertEqual(preview.frame, frame)
                    self.assertEqual([item.frame for item in preview.samples],
                                     list(range(frame, max(-1, frame - 4), -1)))
                    self.assertEqual(len(preview.plots[0].find_withtag("sample")), frame + 1)
                grid.selection.move_to(0, 0)
                grid.selection.move_to(3, 0, extend=True)
                grid.on_select()
                self.assertEqual(preview.frame, 3)  # Active row, not the range's first row.
                self.assertIn("Duration: 4f" if language == "en" else "長さ: 4f",
                              editor.frame_status.cget("text"))
                for _ in range(100):
                    grid._move(0, 1)
                self.assertEqual(preview.frame, 3)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(editor.document.text, original)
                self.assertFalse(editor.document.modified)
                self.assertEqual(source.read_text(encoding="utf-8"), original)
                with self.assertRaises(tk.TclError):
                    editor.text.edit_undo()  # Preview updates added no Undo step.
                self.assertLess(len(preview.plots[0].find_all()), 15)
                self.doCleanups()

    def test_preview_refresh_after_edit_preserves_undo_and_pending_cancel(self):
        root, editor, source = self.make_editor()
        self.wait_for(root, lambda: editor._stick_frames is not None)
        preview, grid = editor.stick_preview, editor.table_grid
        compact_height = preview.winfo_reqheight()
        grid.selected = (0, 1)
        grid.begin_edit(initial="ls(45)")
        root.update()
        self.assertEqual(preview.samples, ())
        self.assertEqual(preview.status.cget("text"), editor.words["preview_updating"])
        self.assertGreater(preview.winfo_reqheight(), compact_height)
        grid.cancel_edit()
        root.update()
        self.assertEqual(preview.frame, 0)
        self.assertEqual(preview.samples[0].left.angle, 0)
        self.assertEqual(preview.status.cget("text"), "")
        self.assertEqual(preview.winfo_reqheight(), compact_height)
        grid.begin_edit(initial="ls(90)")
        grid.commit_edit()
        self.assertEqual(preview.samples, ())
        self.wait_for(root, lambda: editor._stick_frames is not None)
        self.assertEqual(preview.samples[0].left.angle, 90)
        for row in range(4):
            grid.jump_to_row(row)
        self.assertTrue(editor.document.modified)
        self.assertTrue(editor.undo())
        self.assertEqual(editor.document.text, SCRIPT)
        self.assertFalse(editor.document.modified)
        self.assertTrue(editor.redo())
        self.assertIn("ls(90)", editor.document.text.splitlines()[0])
        self.assertEqual(source.read_text(encoding="utf-8"), SCRIPT)

    def test_stale_result_is_ignored_and_failure_clears_preview(self):
        first_started, first_release = threading.Event(), threading.Event()
        second_started, second_release = threading.Event(), threading.Event()
        calls = []

        def delayed(snapshot, **options):
            calls.append(snapshot)
            started, release = ((first_started, first_release) if len(calls) == 1
                                else (second_started, second_release))
            started.set()
            release.wait(5)
            return analyze_positions(snapshot, **options)

        self.addCleanup(first_release.set)
        self.addCleanup(second_release.set)
        with patch("python_to_exe.editor.line_positions.analyze_positions", delayed):
            root, editor, _source = self.make_editor("1\tls(0)\n")
            self.wait_for(root, first_started.is_set)
            editor.show_raw()
            editor.text.delete("1.0", "1.0 lineend")
            editor.text.insert("1.0", "1\tls(90)")
            editor.text.mark_set("insert", "1.0")
            root.update()
            first_release.set()
            self.wait_for(root, second_started.is_set)
            self.assertIsNone(editor._stick_frames)
            self.assertEqual(editor.stick_preview.samples, ())
            self.assertEqual(editor.stick_preview.status.cget("text"), editor.words["preview_updating"])
            second_release.set()
            self.wait_for(root, lambda: editor._stick_frames is not None)
            self.assertEqual(editor.stick_preview.samples[0].left.angle, 90)
            self.assertEqual(len(calls), 2)
        editor.text.delete("1.0", "1.0 lineend")
        editor.text.insert("1.0", "1\tls(")
        root.update()
        self.wait_for(root, lambda: editor._position_job is None and not editor._position_worker_active)
        self.assertIsNone(editor._stick_frames)
        self.assertEqual(editor.stick_preview.samples, ())
        self.assertEqual(editor.stick_preview.status.cget("text"), editor.words["preview_unavailable"])

    def test_closing_during_analysis_releases_icons_on_main_thread(self):
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        destroyed_on = []
        destroy_image = tk.Image.__del__

        def recorded_delete(image):
            destroyed_on.append(threading.current_thread())
            destroy_image(image)

        def delayed(snapshot, **options):
            started.set()
            release.wait(5)
            return analyze_positions(snapshot, **options)

        with patch("python_to_exe.editor.line_positions.analyze_positions", delayed), \
                patch.object(tk.Image, "__del__", recorded_delete):
            root, editor, _source = self.make_editor()
            self.wait_for(root, started.is_set)
            results = editor._position_queue
            editor.destroy()
            self.assertEqual(editor._palette_icons, {})
            self.assertEqual(editor._position_poll_job, None)
            self.assertEqual(destroyed_on, [threading.main_thread()] * 16)
            release.set()
            self.wait_for(root, lambda: not results.empty())
            _revision, result = results.get_nowait()
            self.assertTrue(result.success, result.error)
            self.assertIsNotNone(result.sticks)
            self.assertTrue(editor._closed)
            self.assertEqual(destroyed_on, [threading.main_thread()] * 16)
