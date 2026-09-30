"""Opt-in D0 smoke check: one Tk root/session, JP/EN and normal comparison.

Run only once at the end of D0 verification, on WSLg or a graphical desktop.
All settings, source, backups, recovery, and converter outputs are temporary.
No dialogs or external FTP connections are used.
"""

import gc
import json
from pathlib import Path
import sys
import tempfile
import time
import weakref
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python_to_exe.app_settings import AppSettings
from python_to_exe.dopagaki_app import DopagakiApp
from python_to_exe.editor import theme as normal_theme
from python_to_exe.editor.dopagaki import theme
from python_to_exe.editor.dopagaki.ui import DopagakiEditorWindow
from python_to_exe.editor.tsv_syntax import CANDIDATES
from python_to_exe.editor.window import EditorWindow


def check_session(folder):
    source = folder / "D0 日本語.tsv"
    original = b"1\tls(90)\trs(180)\ta\r\n2\tls(0)\trs(45)\tb\n"
    source.write_bytes(original)
    settings = AppSettings(folder / "settings.json")
    app = DopagakiApp("ja", settings=settings)
    app.withdraw()
    callbacks, messages = [], []
    app.report_callback_exception = lambda kind, value, _trace: callbacks.append(f"{kind.__name__}: {value}")

    def wait_for(condition, timeout=8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.update()
            if callbacks:
                raise AssertionError(callbacks)
            if condition():
                return
            time.sleep(0.005)
        raise AssertionError("Tk smoke check timed out")

    def undo_state(editor):
        return (editor.tk.call(editor.text._w, "edit", "canundo"),
                editor.tk.call(editor.text._w, "edit", "canredo"))

    try:
        jp = app._create_editor(initial_path=source)
        en = DopagakiEditorWindow(app, language="en", initial_path=source, settings=settings)
        normal = EditorWindow(app, language="en", initial_path=source, settings=settings)
        wait_for(lambda: all(editor._positions is not None for editor in (jp, en, normal)))
        assert jp.cget("background") == en.cget("background") == theme.COLORS["app_background"]
        assert normal.cget("background") == normal_theme.COLORS["app_background"]
        for editor in (jp, en, normal):
            assert editor.show_table()
        app.update()
        assert normal.table_grid.canvas.cget("background") == normal_theme.COLORS["panel_background"]
        latencies = []
        for editor in (jp, en):
            grid = editor.table_grid
            before = (editor.document.text, editor.document.modified, undo_state(editor),
                      editor._positions, editor._stick_frames, editor._position_revision)
            started = time.monotonic()
            grid._move(0, 1)
            app.update()
            latencies.append(round((time.monotonic() - started) * 1000, 2))
            assert len(grid.canvas.find_withtag("dopagaki_effect")) == 1
            assert grid.effects.motion.pending
            selection = grid.selection.anchor, grid.selection.active, grid.selection.bounds
            wait_for(lambda: not grid.effects.motion.pending)
            assert grid.canvas.find_withtag("dopagaki_effect") == ()
            assert (grid.selection.anchor, grid.selection.active, grid.selection.bounds) == selection
            assert (editor.document.text, editor.document.modified, undo_state(editor),
                    editor._positions, editor._stick_frames, editor._position_revision) == before

        # Settings menu operates independently of document/history/focus.
        menu = jp.nametowidget(jp.cget("menu"))
        motion_menu = jp.nametowidget(menu.entrycget("end", "menu"))
        for index, level in enumerate(("OFF", "LOW", "MID", "FULL")):
            motion_menu.invoke(index)
            assert AppSettings(settings.path).get("dopagaki_intensity") == level
            jp.table_grid._move(0, 1)
            app.update()
            if level == "OFF":
                assert not jp.table_grid.effects.motion.pending
                assert jp.table_grid.canvas.find_withtag("dopagaki_effect") == ()
            else:
                assert jp.table_grid.effects.motion.pending
                wait_for(lambda: not jp.table_grid.effects.motion.pending)
            assert not jp.document.modified

        # The real Entry/Text undo stack is still the normal editor's stack.
        grid = jp.table_grid
        grid.jump_to_row(0, 3)
        app.update()
        grid.begin_edit()
        entry = grid._editor
        entry.delete(0, "end")
        entry.insert(0, "zl")
        app.update()
        assert entry.winfo_exists() and grid._editor is entry
        assert not jp.document.modified  # Pending Entry content is not committed by motion.
        assert grid.commit_edit()
        assert jp.document.modified and "zl" in jp.document.text
        assert jp.undo() and not jp.document.modified
        assert jp.redo() and jp.document.modified
        assert jp.undo() and not jp.document.modified
        grid.jump_to_row(0, 3)
        grid.insert_candidate(next(item for item in CANDIDATES if item.label == "zl"))
        assert grid.commit_edit()
        assert jp.document.modified
        assert jp.undo() and not jp.document.modified

        grid.selection.move_to(0, 1)
        grid.selection.move_to(1, 3, extend=True)
        grid.on_select()
        grid._schedule_draw()
        app.update()
        bounds = grid.selection.bounds
        wait_for(lambda: not grid.effects.motion.pending)
        assert grid.selection.bounds == bounds
        jp._show_palette_page(2)
        jp._show_palette_page(1)
        grid.canvas.xview_moveto(0.1)
        grid.canvas.yview_moveto(0.1)
        app.update()
        assert not jp.document.modified
        assert jp.show_raw()
        app.update()
        assert not grid.effects.motion.pending
        assert jp.show_table()
        wait_for(lambda: jp._positions is not None and not jp._position_worker_active)
        assert jp.stick_preview.samples

        with patch("tkinter.messagebox.showinfo", side_effect=lambda *args, **_kwargs: messages.append(args)), \
             patch("tkinter.messagebox.showerror", side_effect=lambda *args, **_kwargs: callbacks.append(str(args))):
            assert jp.validate()
            wait_for(lambda: not jp._validation_pending and not app._busy())
            assert jp.words["no_errors"] in jp._problems_title.cget("text")
            app.output_entry.delete(0, "end")
            app.output_entry.insert(0, str(folder))
            app.outname_entry.delete(0, "end")
            app.outname_entry.insert(0, "d0-smoke")
            app.format_var.set("stas")
            assert jp.save_and_convert()
            wait_for(lambda: not app._busy())
            assert app._last_successful_output is not None
            assert app._last_successful_output.is_file()
            assert len(messages) == 1
        assert source.read_bytes() == original

        # Repeat real Canvas-item/callback allocation without reopening windows.
        grid.jump_to_row(0, 0)
        app.update()
        wait_for(lambda: not grid.effects.motion.pending)
        commands_before = len(grid._tclCommands)
        for index in range(100):
            grid.jump_to_row(index % 2, index % 3)
            app.update()
            assert len(grid.canvas.find_withtag("dopagaki_effect")) <= 1
        wait_for(lambda: not grid.effects.motion.pending)
        assert len(grid._tclCommands) == commands_before

        # Close during an active pulse, including Tk's registered timer command.
        grid._move(0, 1)
        app.update()
        motion = grid.effects.motion
        generation, job = motion._generation, motion._job
        assert job is not None
        timer_command = app.tk.call("after", "info", job)[0]
        references = [weakref.ref(widget) for widget in (jp, grid, motion, en, normal)]
        jp.destroy()
        assert job not in app.tk.call("after", "info")
        assert not app.tk.call("info", "commands", timer_command)
        motion._tick(generation)  # Even a late saved callback is harmless.
        en.destroy()
        normal.destroy()
        del jp, en, normal, grid, motion, editor, entry, menu, motion_menu
        app.update()
        gc.collect()
        assert all(reference() is None for reference in references)
        assert not callbacks, callbacks
        return dict(tk=app.tk.call("info", "patchlevel"), sessions=1, languages=["ja", "en"],
                    normal_theme="unchanged", pulse_start_ms=latencies, real_moves=100,
                    checks="pulse/intensity/Entry/Undo/selection/Palette/Stick/scroll/Raw/Validate/Convert/cleanup",
                    collected_editors=True, pending_effect_callbacks=0)
    finally:
        app.destroy()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="dopagaki-d0-tk-") as directory:
        print(json.dumps(check_session(Path(directory)), ensure_ascii=False, indent=2))
