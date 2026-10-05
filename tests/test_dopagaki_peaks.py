"""Dopagaki3 Phase 3 (dopagaki3.md §15 P3): true results, Validate / F7 / F5 / F8, COVER."""

import gc
import tempfile
import threading
import time
import tkinter as tk
import unittest
import weakref
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from python_to_exe.app_settings import AppSettings
from python_to_exe.converter_gui import TASConverterApp
from python_to_exe.converter_logic import ConversionOutputs
from python_to_exe.editor.dopa.heat import HeatState
from python_to_exe.editor.dopa.outcome import (FAILED, SEND_CONFIRMED, SEND_UNVERIFIED, SUCCESS,
                                               classify_conversion)
from python_to_exe.editor.validation import ValidationResult
from python_to_exe.editor.window import EditorWindow


SCRIPT = "5\tls(90)\n1\ta\trs(0)\n2\tzl\n"


class OutcomeTests(unittest.TestCase):
    def test_classification_follows_only_the_parent_result_and_upload_line(self):
        self.assertEqual(classify_conversion(False, True, "Script successfully uploaded"), FAILED)
        self.assertEqual(classify_conversion(True, False, ""), SUCCESS)
        self.assertEqual(classify_conversion(
            True, True, "Script successfully generated\nScript successfully uploaded\n"),
            SEND_CONFIRMED)
        # tsv-tas.py exits 0 after "FTP error"; only the upload line confirms a send.
        self.assertEqual(classify_conversion(True, True, "Script successfully generated\nFTP error\n"),
                         SEND_UNVERIFIED)
        self.assertEqual(classify_conversion(True, True, "not Script successfully uploaded"),
                         SEND_UNVERIFIED)
        self.assertEqual(classify_conversion(True, True, None), SEND_UNVERIFIED)

    def test_round_settles_only_after_productive_actions(self):
        heat = HeatState()
        self.assertIsNone(heat.settle())
        heat.productive(1.0)
        heat.productive(2.0)
        gained, intensity = heat.dopa, heat.intensity
        bonus = heat.settle()
        self.assertEqual(bonus, round(gained * (0.5 + intensity)))
        self.assertEqual((heat.round, heat.actions, heat.combo, heat.dopa), (2, 0, 0, gained + bonus))


def tk_root(case):
    try:
        root = tk.Tk()
    except tk.TclError as error:
        case.skipTest(f"graphical Tk display unavailable: {error}")
    root.withdraw()
    case.errors = []
    root.report_callback_exception = lambda *error: case.errors.append(error)
    return root


class ConverterPlumbingTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        try:
            self.app = TASConverterApp("en", settings=AppSettings(self.folder / "settings.json"))
        except tk.TclError as error:
            self.skipTest(f"graphical Tk display unavailable: {error}")
        self.app.withdraw()
        self.addCleanup(self.app.destroy)

    def test_requester_hears_the_result_before_the_unchanged_dialog(self):
        order = []
        editor = SimpleNamespace(winfo_exists=lambda: True,
                                 conversion_finished=lambda *args, **kw: order.append(("editor", args)))
        outputs = ConversionOutputs(self.folder / "route.stas", ftp_requested=True)
        self.app._conversion_listener = lambda: editor
        self.app._conversion_format = "stas"
        for event in (("log", "Script successfully uploaded"),
                      ("stdout", "Script successfully generated\nScript successfully uploaded\n"),
                      ("success", outputs), ("done", None)):
            self.app._events.put(event)
        with patch("python_to_exe.converter_gui.messagebox.showinfo",
                   side_effect=lambda *args: order.append(("dialog", args))):
            self.app._drain_events()
        self.assertEqual([kind for kind, _ in order], ["editor", "dialog"])
        self.assertEqual(order[0][1], (True, outputs,
                                       "Script successfully generated\nScript successfully uploaded\n",
                                       "stas"))
        self.assertIsNone(self.app._conversion_listener)
        self.assertIn("Script successfully uploaded", self.app.log_text.get("1.0", "end"))

    def test_failure_closed_editor_and_raising_editor_never_block_the_dialog(self):
        calls = []
        broken = SimpleNamespace(winfo_exists=lambda: True,
                                 conversion_finished=Mock(side_effect=RuntimeError("fx")))
        for listener in (lambda: None, lambda: SimpleNamespace(winfo_exists=lambda: False),
                         lambda: broken):
            self.app._conversion_listener = listener
            self.app._events.put(("error", "boom"))
            self.app._events.put(("done", None))
            with patch("python_to_exe.converter_gui.messagebox.showerror",
                       side_effect=lambda *args: calls.append(args)), \
                 patch("python_to_exe.converter_gui.traceback.print_exc"):
                self.app._drain_events()
        self.assertEqual(len(calls), 3)
        broken.conversion_finished.assert_called_once_with(False, None, "", None, error="boom",
                                                           stderr="", started=True)

    def test_real_f5_reaches_only_the_requesting_editor(self):
        class ImmediateThread:
            def __init__(self, target, args=(), daemon=None):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        source = self.folder / "route.tsv"
        source.write_text(SCRIPT, encoding="utf-8")
        editor = self.app._create_editor(initial_path=str(source))
        other = self.app._create_editor()
        self.addCleanup(other.destroy)
        editor.show_table()
        self.app.update()
        received = []
        other.conversion_finished = lambda *args, **kw: received.append(("other", args))
        original = editor.conversion_finished
        editor.conversion_finished = lambda *args, **kw: (received.append(("editor", args)),
                                                          original(*args, **kw))[1]
        self.app.output_entry.insert(0, str(self.folder))
        with patch("python_to_exe.converter_gui.threading.Thread", ImmediateThread), \
             patch("python_to_exe.converter_gui.messagebox.showinfo") as dialog:
            editor.table_grid.jump_to_row(1, column=3)
            editor.table_grid.begin_edit(initial="zr")
            editor.table_grid.commit_edit()
            self.assertTrue(editor.save_and_convert())
            self.app._drain_events()
        dialog.assert_not_called()  # P4: the requesting Editor presents it (non-modal).
        self.assertEqual([who for who, _ in received], ["editor"])
        self.assertIs(received[0][1][0], True)
        self.assertEqual(received[0][1][1].primary, self.folder / "route")
        self.assertEqual(editor._dopa.heat.round, 2)  # Real local output: the round settles.
        self.assertIsNone(self.app._conversion_listener)


class PeakTests(unittest.TestCase):
    def make_editor(self, **values):
        root = tk_root(self)
        self.addCleanup(root.destroy)
        folder = tempfile.TemporaryDirectory(prefix="tas peaks ")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        source = self.folder / "route.tsv"
        source.write_text(SCRIPT, encoding="utf-8")
        root._tas_app_settings = AppSettings(self.folder / "settings.json")
        if values:
            root._tas_app_settings.update(**values)
        self.on_convert = Mock(return_value=True)
        editor = EditorWindow(root, language="en", initial_path=source, on_convert=self.on_convert,
                              on_validate=Mock(return_value=True), on_analyze=Mock(return_value=True))
        editor.geometry("1200x700")
        editor.show_table()
        root.update()
        self.root, self.editor = root, editor
        self.now = [100.0]
        director = editor._dopa
        director.clock = director.fx.clock = lambda: self.now[0]
        self.shouts = []
        shout = director.hud.shout
        director.hud.shout = lambda text, tier, **kw: (self.shouts.append(text),
                                                       shout(text, tier, **kw))
        return root, editor, director

    def advance(self, seconds):
        steps = max(1, int(seconds / 0.05))
        for _ in range(steps):
            self.now[0] += seconds / steps
            self.editor._dopa.fx.step()
        self.root.update()

    def card_texts(self, cover):
        canvas = cover.canvas
        return {canvas.itemcget(item, "text") for item in canvas.find_withtag("card")
                if canvas.type(item) == "text"}

    def assert_idle(self):
        # The METER lamp pulses while a real position analysis runs; wait for it.
        deadline = time.monotonic() + 10
        while self.editor._position_unavailable_message() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.advance(3.0)
        engine = self.editor._dopa.fx
        engine._tick()
        self.assertEqual(engine.active, ())
        self.assertIsNone(engine._job)  # Nothing keeps a timer alive afterwards.

    def outputs(self, send):
        return ConversionOutputs(self.folder / "route", ftp_requested=send)

    def commit(self, row, column, value):
        grid = self.editor.table_grid
        grid.jump_to_row(row, column=column)
        grid.begin_edit(initial=value)
        grid._entry_move(SimpleNamespace(widget=grid._editor), 0, 1)

    def test_validate_shows_scan_only_while_running_and_judges_current_results(self):
        root, editor, director = self.make_editor()
        meter, hud = editor.meter_canvas, director.hud
        self.commit(0, 2, "a")
        self.commit(1, 3, "b")
        self.assertTrue(editor.validate())
        self.assertEqual(meter.itemcget(hud.process_text, "text"), "SCAN")
        receive = editor.on_validate.call_args[0][1]
        receive(ValidationResult(True))
        self.assertEqual(meter.itemcget(hud.process_text, "text"), "")
        self.assertIn("NO ERRORS!!", self.shouts)
        self.assertTrue(editor.validate())
        editor.on_validate.call_args[0][1](ValidationResult(False, stderr="Error: x"))
        self.assertEqual((director.heat.combo, director.heat.actions), (0, 2))  # Only the combo.
        self.assertEqual(self.shouts[-1], "SO CLOSE!")
        self.assertTrue(editor.validate())
        callback = editor.on_validate.call_args[0][1]
        self.commit(2, 2, "c")  # The document changes before the result arrives.
        before = list(self.shouts)
        callback(ValidationResult(True))
        self.assertEqual(self.shouts, before)  # Stale: factual text only.
        self.assertEqual(meter.itemcget(hud.process_text, "text"), "")
        self.assert_idle()

    def test_f7_success_names_the_real_total(self):
        root, editor, director = self.make_editor()
        self.assertTrue(editor.analyze_frames())
        frames = SimpleNamespace(total_frames=12345, rows=(), headers=())
        result = SimpleNamespace(success=True, frames=frames, report=ValidationResult(True))
        with patch("python_to_exe.editor.frame_inspector.FrameInspector"):
            editor.on_analyze.call_args[0][1](result)
        self.assertEqual(self.shouts[-1], "12,345F SCANNED!!")
        self.assertEqual(editor.meter_canvas.itemcget(director.hud.process_text, "text"), "")

    def test_f5_stamps_save_runs_rays_and_settles_only_on_success(self):
        root, editor, director = self.make_editor()
        self.commit(0, 2, "a")
        self.assertTrue(editor.save_and_convert())
        self.on_convert.assert_called_with(editor.document.path, send_ftp=False)
        self.assertIn("SAVE ★", self.shouts)
        self.assertEqual(editor.meter_canvas.itemcget(director.hud.process_text, "text"),
                         "CONVERTING")
        self.assertTrue(editor.reward_canvas.find_withtag("process_rays"))
        editor.conversion_finished(False)
        self.assertEqual(self.shouts[-1], "SO CLOSE!")
        self.assertEqual(director.heat.round, 1)
        self.assertFalse(editor.reward_canvas.find_withtag("process_rays"))
        self.assertTrue(editor.save_and_convert())
        editor.conversion_finished(True, self.outputs(False), "", "binary")
        self.assertEqual(self.shouts[-1], "CONVERTED!!")
        self.assertEqual((director.heat.round, director.heat.actions), (2, 0))
        self.assertEqual(editor.document.text, "5\tls(90)\ta\n1\ta\trs(0)\n2\tzl\n")
        self.assert_idle()

    def test_f8_cover_counts_real_time_then_shows_only_facts(self):
        root, editor, director = self.make_editor()
        self.commit(0, 2, "a")
        focus = editor.focus_get()
        self.assertTrue(editor.save_convert_and_send())
        cover = director.cover
        self.assertIsNotNone(cover)
        self.assertIs(editor.focus_get(), focus)  # The COVER never takes focus.
        self.advance(2.4)
        self.assertEqual(cover.canvas.itemcget(cover.caption, "text"),
                         "Converting + sending… 2.4s")
        self.assertIsNotNone(cover.orb)  # 溜め after 1.2s of real waiting.
        editor.conversion_finished(True, self.outputs(True),
                                   "Script successfully generated\nScript successfully uploaded\n",
                                   "stas")
        texts = self.card_texts(cover)
        self.assertTrue({"route", "STAS", "TO  SMO/tas/scripts/route"} <= texts)
        self.advance(1.1)
        self.assertEqual([cover.canvas.itemcget(star, "text") for _, star in cover.stars],
                         ["★", "★", "★"])
        self.assertEqual(director.heat.round, 2)
        self.advance(1.0)
        self.assertIsNone(director.cover)
        self.assertFalse(cover.canvas.winfo_exists())
        self.assertNotIn(cover._tag, editor.table_grid.canvas.bindtags())
        self.assert_idle()
        self.assertEqual(self.errors, [])

    def test_f8_unverified_and_failure_never_claim_a_send(self):
        root, editor, director = self.make_editor()
        self.commit(0, 2, "a")
        self.assertTrue(editor.save_convert_and_send())
        cover = director.cover
        editor.conversion_finished(True, self.outputs(True),
                                   "Script successfully generated\nFTP error\n", "binary")
        self.advance(1.0)
        texts = self.card_texts(cover)
        self.assertIn("SEND: UNVERIFIED (see log)", texts)
        self.assertIn("BUILT", texts)
        self.assertEqual([cover.canvas.itemcget(star, "text") for _, star in cover.stars],
                         ["★", "★", "☆"])
        self.assertFalse(cover.canvas.find_withtag("rays"))
        self.assertNotIn("SENT!!", self.shouts)
        self.assertEqual(director.heat.round, 1)  # The send is not a fact: no settlement.
        self.advance(2.0)
        self.assertIsNone(director.cover)
        self.assertTrue(editor.save_convert_and_send())
        cover = director.cover
        editor.conversion_finished(False)
        self.assertEqual(director.heat.combo, 0)
        self.advance(1.0)
        self.assertIsNone(director.cover)
        self.assert_idle()

    def test_any_key_closes_the_cover_and_still_reaches_the_table(self):
        root, editor, director = self.make_editor()
        editor.focus_force()
        editor.table_grid.canvas.focus_set()
        root.update()
        editor.table_grid.jump_to_row(2, column=2)
        self.assertTrue(editor.save_convert_and_send())
        cover = director.cover
        editor.table_grid.canvas.event_generate("<KeyPress>", keysym="x")
        root.update()
        self.assertIsNone(director.cover)
        self.assertFalse(cover.canvas.winfo_exists())
        self.assertEqual(editor.table_grid._editor.get(), "x")  # The key did its normal job.
        editor.table_grid.cancel_edit()
        self.assertNotIn(cover._tag, editor.table_grid.canvas.bindtags())
        editor.conversion_finished(True, self.outputs(True), "Script successfully uploaded\n", "binary")
        self.assertEqual(self.shouts[-1], "SENT!!")  # Closed early: HUD-only result.

    def test_work_focus_shows_f8_result_without_a_cover(self):
        root, editor, director = self.make_editor(dopa_motion=0)
        self.assertTrue(editor.save_convert_and_send())
        self.assertIsNone(director.cover)
        editor.conversion_finished(True, self.outputs(True), "FTP error\n", "binary")
        self.assertEqual(self.shouts[-1], "BUILT")
        self.assert_idle()

    def test_destroy_with_open_cover_cleans_up_and_releases_the_editor(self):
        root, editor, director = self.make_editor()
        self.assertTrue(editor.save_convert_and_send())
        self.advance(0.5)
        reference = weakref.ref(editor)
        editor.destroy()
        root.update()
        self.assertEqual(self.errors, [])
        del editor, director
        self.editor = None
        gc.collect()
        self.assertIsNone(reference())


if __name__ == "__main__":
    unittest.main()
