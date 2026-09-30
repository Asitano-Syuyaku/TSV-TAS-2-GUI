"""D1 opt-in real Tk interaction/stress check, JP/EN, temporary files only."""

import gc
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tkinter as tk
import weakref

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python_to_exe.app_settings import AppSettings
from python_to_exe.dopagaki_app import DopagakiApp
from python_to_exe.editor.dopagaki.ui import DopagakiEditorWindow
from python_to_exe.editor.tsv_syntax import CANDIDATES, PALETTE_PAGES


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def exercise(app, editor, capture=None):
    grid, effects = editor.table_grid, editor.table_grid.effects
    errors = []
    effect_refs = []
    app.report_callback_exception = lambda kind, value, _trace: errors.append(f"{kind.__name__}: {value}")

    def pump():
        app.update()
        assert not errors, errors
        jobs = app.tk.call("after", "info")
        motion_jobs = [job for job in jobs
                       if str(app.tk.call("after", "info", job)[0]).endswith("tick")]
        assert len(motion_jobs) <= 1
        if effects.motion.pending:
            assert effects.motion._job in motion_jobs
            assert len(effects.motion.effect.tracks) <= 8
            effect_refs.extend(weakref.ref(effect) for effect, _start in effects.motion.effect.tracks.values())

    def wait_for(condition):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            pump()
            if condition():
                return
            time.sleep(0.003)
        raise AssertionError("D1 Tk check timed out")

    def idle():
        wait_for(lambda: not effects.motion.pending)
        assert effects.motion.effect is None
        assert not grid.canvas.find_withtag("dopagaki_effect")
        assert all(not canvas.find_withtag("dopagaki_ring") for canvas in editor.stick_preview.plots)
        gc.collect()
        assert all(reference() is None for reference in effect_refs)
        effect_refs.clear()

    def history():
        return tuple(editor.tk.call(editor.text._w, "edit", action) for action in ("canundo", "canredo"))

    wait_for(lambda: editor._positions is not None)
    assert editor.show_table()
    editor.lift()
    grid.canvas.focus_force()
    pump()
    idle()
    original, before_history = editor.document.text, history()
    positions, sticks = editor._positions, editor._stick_frames
    command_count = len(grid._tclCommands)
    delays = []

    # Real registered keyboard bindings, including fast alternating arrows.
    for index in range(1000):
        started = time.monotonic()
        grid.canvas.event_generate("<Right>" if index % 2 == 0 else "<Left>")
        pump()
        delays.append((time.monotonic() - started) * 1000)
        assert effects.effect_for("cell") is not None
        assert len(grid.canvas.find_withtag("dopagaki_effect")) <= 1
        assert len(effects.motion.effect.tracks) <= 8
    assert editor.document.text == original and not editor.document.modified
    assert history() == before_history
    assert editor._positions is positions and editor._stick_frames is sticks
    idle()

    # F2, Tab/Enter and their Shift variants all use the original apply path.
    for key in ("<Tab>", "<Return>", "<Shift-Tab>", "<Shift-Return>"):
        grid.jump_to_row(0, 3)
        grid.canvas.focus_force()
        pump()
        grid.canvas.event_generate("<F2>")
        pump()
        entry = grid._editor
        assert entry is not None
        entry.delete(0, "end")
        entry.insert(0, "zl")
        entry.focus_force()
        pump()
        entry.event_generate(key)
        pump()
        assert grid._editor is None, (key, app.focus_get(), entry.get())
        assert effects.effect_for("commit") is not None
        assert editor.document.modified
        assert editor.undo() and editor.document.text == original
        assert editor.redo() and editor.document.modified
        assert editor.undo() and not editor.document.modified
    grid.jump_to_row(0, 3)
    grid.begin_edit()
    assert grid.commit_edit()  # No-op commit must not emit a stronger effect.
    effects.remove("commit")
    grid.begin_edit()
    assert grid.commit_edit() and effects.effect_for("commit") is None

    # Click commit and selection hit-testing while feedback is active.
    grid.begin_edit()
    grid._editor.delete(0, "end")
    grid._editor.insert(0, "zl")
    x1, y1, x2, y2 = grid._cell_box(1, 3)
    grid.canvas.event_generate("<Button-1>", x=int((x1 + x2) / 2 - grid.canvas.canvasx(0)),
                               y=int((y1 + y2) / 2 - grid.canvas.canvasy(0)))
    pump()
    assert grid.selected == (1, 3) and effects.effect_for("commit") is not None
    assert editor.undo() and editor.document.text == original

    for index in range(300):
        grid.jump_to_row(0, 3)
        grid.begin_edit()
        grid._editor.delete(0, "end")
        grid._editor.insert(0, "zl" if index % 2 == 0 else "zr")
        assert grid.commit_edit()
        pump()
        assert effects.effect_for("commit") is not None
        assert len(grid.canvas.find_withtag("dopagaki_effect")) <= 2
    assert editor.undo()  # Also ensure normal undo still operates after the burst.
    while editor.document.text != original:
        assert editor.undo()

    buttons = {}
    for number, categories in enumerate(PALETTE_PAGES, start=1):
        editor._show_palette_page(number)
        pump()
        candidates = [item for category in categories for item in CANDIDATES if item.category == category]
        page_buttons = [widget for widget in descendants(editor._palette_pages[number - 1][0])
                        if isinstance(widget, tk.Button)]
        assert len(candidates) == len(page_buttons)
        buttons.update({candidate.label: button for candidate, button in zip(candidates, page_buttons)})
    editor._show_palette_page(1)
    pump()
    button = buttons["a"]
    image = button.cget("image")
    button_commands = tuple(button._tclCommands)
    for _index in range(300):
        grid.cancel_edit()
        grid.jump_to_row(0, 3)
        button.invoke()
        pump()
        assert grid._editor.get() == "a" and button.cget("image") == image
        assert tuple(button._tclCommands) == button_commands
        assert effects.effect_for("palette") is not None
    grid.cancel_edit()

    for index in range(300):
        column = index % 2
        grid.cancel_edit()
        grid.jump_to_row(0, column + 1)
        buttons["ls(angle)" if column == 0 else "rs(angle)"].invoke()
        pump()
        entry = grid._editor
        assert entry.get() == ("ls(0)" if column == 0 else "rs(0)")
        assert (entry.index("sel.first"), entry.index("sel.last")) == (3, 4)
        assert effects.effect_for(f"stick{column}") is not None
        assert len(editor.stick_preview.plots[column].find_withtag("dopagaki_ring")) == 1
    grid.cancel_edit()
    wait_for(lambda: editor._positions is not None and not editor._position_worker_active)
    assert editor.document.text == original

    # The page pager keeps pending Entry text, placeholder selection and scroll.
    grid.begin_edit()
    entry = grid._editor
    entry.select_range(0, 1)
    pending = entry.get(), entry.index("sel.first"), entry.index("sel.last"), history()
    for index in range(100):
        editor._show_palette_page(2 if index % 2 == 0 else 1)
        pump()
        assert grid._editor is entry
        assert (entry.get(), entry.index("sel.first"), entry.index("sel.last"), history()) == pending
    grid.cancel_edit()

    grid.jump_to_row(0, 0)
    pump()
    idle()
    total_color = editor.frame_status.value_labels[3].cget("foreground")
    grid.jump_to_row(1, 0)
    pump()
    position = editor._positions.for_line(2)
    expected = (f"{position.start}f", f"{position.duration}f", f"{position.end}f",
                f"{editor._positions.total_frames}f")
    assert editor.frame_status._values == expected
    assert editor.frame_status.value_labels[3].cget("foreground") == total_color
    assert effects.effect_for("frame") is not None

    grid.selection.move_to(0, 0)
    grid.selection.move_to(3, 3, extend=True)
    grid._schedule_draw()
    grid.on_select()
    pump()
    bounds = grid.selection.bounds
    idle()
    assert grid.selection.bounds == bounds
    # Real row-header hit test, then scroll/resize with an Entry open.
    grid.canvas.event_generate("<Button-1>", x=10, y=grid.header_height + 12)
    pump()
    assert grid._selection_axis == "row"
    grid.jump_to_row(1, 2)
    grid.begin_edit()
    entry = grid._editor
    for size in ("1000x650", "1400x800", "1200x700"):
        editor.geometry(size)
        pump()
        assert grid._editor is entry and entry.winfo_exists()
        assert entry.winfo_width() > 0 and entry.winfo_height() > 0
    grid.cancel_edit()
    grid.canvas.xview_moveto(0.1)
    grid.canvas.yview_moveto(0.1)
    pump()
    assert editor.show_raw()
    pump()
    idle()
    assert editor.show_table()
    grid.jump_to_row(0, 3)
    pump()

    for level in ("OFF", "LOW", "MID", "FULL"):
        editor._motion_intensity.set(level)
        editor._intensity_changed()
        buttons["ls(angle)"].invoke()
        grid.cancel_edit()
        editor._show_palette_page(2)
        pump()
        if level == "OFF":
            assert not effects.motion.pending
        else:
            assert effects.motion.pending
        editor._show_palette_page(1)
        pump()
        if capture is not None and level in ("LOW", "FULL"):
            editor.palette_canvas.yview_moveto(1.0)
            grid.jump_to_row(1, 1)
            buttons["ls(angle)"].invoke()
            pump()
            capture(editor, level)
            grid.cancel_edit()
        idle()
        assert editor.document.text == original and not editor.document.modified
    assert len(grid._tclCommands) == command_count
    assert not errors
    # Leave simultaneous effects active so the caller tests destruction mid-tick.
    buttons["rs(angle)"].invoke()
    grid._move(0, 1)
    pump()
    return dict(cell_moves=1000, commits=300, palette_inserts=300, pages=100, stick_inputs=300,
                pulse_start_ms_median=round(statistics.median(delays), 2),
                pulse_start_ms_max=round(max(delays), 2), callback_cap=1,
                focus_and_entry="preserved", idle_callbacks=0)


def check_session(folder, capture=None):
    source = folder / "D1 日本語.tsv"
    original = (b"1\tls(0)\trs(90)\ta\r\n2\tls(90)\trs(180)\tb\n"
                b"3\tls(180)\trs(270)\tx\n4\tls(270)\trs(0)\ty\n") * 30
    source.write_bytes(original)
    app = DopagakiApp("ja", settings=AppSettings(folder / "settings.json"))
    app.withdraw()
    reports = {}
    try:
        for language in ("ja", "en"):
            editor = DopagakiEditorWindow(app, language=language, initial_path=source)
            reports[language] = exercise(app, editor, capture)
            refs = [weakref.ref(value) for value in (editor, editor.table_grid, editor.table_grid.effects)]
            controller = editor.table_grid.effects.motion
            job = controller._job
            editor.destroy()
            assert job not in app.tk.call("after", "info")
            assert controller.effect is None and not controller.pending
            del editor, controller
            app.update()
            gc.collect()
            assert all(reference() is None for reference in refs)
            reports[language]["closed_editor_collected"] = True
            print(json.dumps({language: reports[language]}, ensure_ascii=False), flush=True)
        assert source.read_bytes() == original
        return reports
    finally:
        app.destroy()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="dopagaki-d1-tk-") as directory:
        check_session(Path(directory))
