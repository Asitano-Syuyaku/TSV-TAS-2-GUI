"""Thin Tk adapters for the existing grid/editor; all editing logic is inherited."""

import tkinter as tk
from tkinter import filedialog, simpledialog

from ..grid import TableGrid
from ..window import EditorWindow
from . import theme
from .effects import CellEffects
from .motion import Intensity
from .widgets import DopagakiStickPreview, FrameValues
from .juice import HypeMeter
from .audio import AudioSettings, create_audio_backend
from .ritual import ConvertRitual
from .ritual_view import RitualView


class DopagakiTableGrid(TableGrid):
    ui_theme = theme

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.effects = CellEffects(self, self.canvas)
        self.bind("<Unmap>", self._pause_effects)

    def _visible_active_box(self, cell=None):
        x1, y1, x2, y2 = self._cell_box(*(self.selected if cell is None else cell))
        x0, y0 = self.canvas.canvasx(0), self.canvas.canvasy(0)
        x1 = max(x1, x0 + self.gutter_width) + 2
        y1 = max(y1, y0 + self.header_height) + 2
        x2 = min(x2, x0 + self.canvas.winfo_width()) - 2
        y2 = min(y2, y0 + self.canvas.winfo_height()) - 2
        return (x1, y1, x2, y2) if x1 < x2 and y1 < y2 else None

    def _draw_visible(self):
        super()._draw_visible()
        effects = getattr(self, "effects", None)
        if effects is not None and self.winfo_exists():
            if effects.particles is not None and effects.particles.particles:
                effects.particles.sync_viewport("grid")
                effects.particles.raise_surface("grid")
            # The normal draw/selection path remains authoritative. Only observe
            # its result, including clipping after scroll/column resize.
            effects.sync_cell(self.selected, self._visible_active_box() if self.winfo_ismapped() else None)
            commit = effects.effect_for("commit")
            if commit is not None:
                commit.relocate(self._visible_active_box(commit.cell) if self.winfo_ismapped() else None)
            view = effects._ritual() if effects._ritual is not None else None
            if view is not None:
                view.repaint()

    def _apply_editor_value(self):
        cell = self.selected
        previous = self.model.cell(*cell)
        result = super()._apply_editor_value()
        effects = getattr(self, "effects", None)
        if result and self.model.cell(*cell) != previous and effects is not None and self.winfo_ismapped():
            effects.commit(cell, self._visible_active_box(cell))
        return result

    def _bind_entry_navigation(self, editor):
        super()._bind_entry_navigation(editor)
        # X11/WSLg reports Shift+Tab as ISO_Left_Tab. Reuse the registered
        # Shift+Tab script so both key names reach the same commit/move path.
        editor.bind("<ISO_Left_Tab>", editor.bind("<Shift-Tab>"))

    def _operation_feedback(self, result, previous):
        if result and self.model.to_text() != previous and self.winfo_ismapped():
            box = self._visible_active_box()
            if box is not None and self.effects is not None:
                self.effects.interaction("operation", origin=(box[2] - 5, box[1] + 5))
        return result

    def paste_text(self, data):
        previous = self.model.to_text()
        return self._operation_feedback(super().paste_text(data), previous)

    def duplicate_row(self):
        previous = self.model.to_text()
        return self._operation_feedback(super().duplicate_row(), previous)

    def _pause_effects(self, event):
        if event.widget is self and self.effects is not None:
            self.effects.motion.clear()

    def close_effects(self):
        effects, self.effects = getattr(self, "effects", None), None
        if effects is not None:
            effects.close()

    def _on_destroy(self, event):
        if event.widget is self:
            self.close_effects()
            # A Tk Variable owns its trace command independently of widgets.
            # Removing widget commands alone leaves this callback holding the
            # grid and its Editor after a cell has been edited.
            value = getattr(self, "_entry_value", None)
            trace = getattr(self, "_entry_value_trace", None)
            if value is not None and trace is not None:
                try:
                    value.trace_remove("write", trace)
                except tk.TclError:
                    pass
            self._entry_value_trace = None
            self._entry_value = None
        super()._on_destroy(event)


class DopagakiEditorWindow(EditorWindow):
    ui_theme = theme
    table_grid_class = DopagakiTableGrid
    stick_preview_class = DopagakiStickPreview

    def __init__(self, master, language="en", *args, **kwargs):
        super().__init__(master, language, *args, **kwargs)
        self._motion_intensity = tk.StringVar(
            self, value=self.settings.get("dopagaki_intensity", "MID"))
        self.table_grid.effects.motion.set_intensity(self._motion_intensity.get())
        previous = self.frame_status
        self.frame_status = FrameValues(previous.master, self._theme_fonts,
                                        self.table_grid.effects, previous.cget("text"))
        self.frame_status.pack(before=previous, **previous.pack_info())
        previous.destroy()
        body = self._palette_pages[0][0].master
        self.hype_meter = HypeMeter(self.input_palette, self._theme_fonts["small"], body)
        self.table_grid.effects.attach_juice(
            self.hype_meter, self.input_palette,
            left=self.table_grid.gutter_width, top=self.table_grid.header_height)
        self.stick_preview.attach_effects(self.table_grid.effects)
        self._audio_settings = AudioSettings(self.settings.path.with_name("dopagaki_audio.json")
                                             if self.settings.path is not None else None)
        banner = tk.Canvas(self.status, highlightthickness=0, borderwidth=0, takefocus=False,
                           background=theme.COLORS["secondary_background"])
        self.ritual_view = RitualView(self, banner=banner,
                                      family=self._theme_fonts["heading"].actual("family"))
        self.table_grid.effects.attach_ritual(self.ritual_view)
        config = self._audio_settings.config
        self.ritual = ConvertRitual(self, self.ritual_view, config=config,
                                    backend=create_audio_backend(config))
        self._normal_convert = self.on_convert
        if self.on_convert is not None:
            self.on_convert = self._convert_with_ritual
        menu = self.nametowidget(self.cget("menu"))
        motion_menu = tk.Menu(menu, tearoff=False, background=theme.COLORS["panel_background"],
                              foreground=theme.COLORS["text"],
                              activebackground=theme.COLORS["accent"],
                              activeforeground=theme.COLORS["panel_background"])
        for level in Intensity:
            motion_menu.add_radiobutton(label=level.value, value=level.value,
                                       variable=self._motion_intensity,
                                       command=self._intensity_changed)
        label = "演出の強さ" if language == "ja" else "Motion intensity"
        self._audio_enabled = tk.BooleanVar(self, value=config.enabled)
        audio_menu = tk.Menu(menu, tearoff=False, background=theme.COLORS["panel_background"],
                             foreground=theme.COLORS["text"])
        jp = language == "ja"
        audio_menu.add_checkbutton(label="音楽を有効化" if jp else "Enable audio",
                                   variable=self._audio_enabled, command=self._audio_changed)
        audio_menu.add_command(label="音源を選択…" if jp else "Choose local audio…",
                               command=lambda: self._choose_audio("path"))
        audio_menu.add_command(label="ffplayを選択…" if jp else "Choose ffplay…",
                               command=lambda: self._choose_audio("player"))
        audio_menu.add_command(label="同期補正（ms）…" if jp else "Sync offset (ms)…",
                               command=self._choose_audio_offset)
        audio_menu.add_separator()
        audio_menu.add_command(label="F5演出を停止" if jp else "Cancel F5 effects",
                               command=self.ritual.cancel)
        menu.add_cascade(label="Dopagaki: F5 " + ("音楽" if jp else "audio"), menu=audio_menu)
        menu.add_cascade(label="Dopagaki: " + label, menu=motion_menu)
        self.bind("<Unmap>", self._pause_micro)

    def _pause_micro(self, event):
        if event.widget is self and self.table_grid.effects is not None:
            ritual = getattr(self, "ritual", None)
            if ritual is not None:
                ritual.cancel()
            self.table_grid.effects.motion.clear()

    def _convert_with_ritual(self, path, send_ftp=False):
        # Existing commit/save/arguments/worker start run first. No audio path
        # lookup, process stop/start, or ritual effect can delay the converter.
        started = self._normal_convert(path, send_ftp=send_ftp)
        if started and not send_ftp:
            try:
                self.ritual.start(self.table_grid.effects.motion.intensity)
                observe = getattr(self.master, "observe_conversion", None)
                if observe is not None:
                    observe(self.ritual.receiver())
            except Exception:
                self.ritual.cancel()
                import traceback
                traceback.print_exc()
        return started

    def _audio_changed(self):
        self._audio_settings.update(enabled=self._audio_enabled.get())
        self.ritual.config = self._audio_settings.config
        if not self.ritual.config.enabled:
            self.ritual.stop_audio()

    def _choose_audio(self, key):
        selected = filedialog.askopenfilename(parent=self, filetypes=(
            [("Audio", "*.webm *.opus *.m4a *.mp3 *.wav"), ("All files", "*")]
            if key == "path" else [("ffplay", "ffplay ffplay.exe"), ("All files", "*")]))
        if selected:
            self._audio_settings.update(**{key: selected})
            self._reset_audio_backend()

    def _choose_audio_offset(self):
        value = simpledialog.askinteger("Dopagaki", "audio_sync_offset_ms (+ = later visual)",
                                        parent=self, initialvalue=self._audio_settings.config.sync_offset_ms,
                                        minvalue=-2000, maxvalue=2000)
        if value is not None:
            self._audio_settings.update(sync_offset_ms=value)
            self._reset_audio_backend()

    def _reset_audio_backend(self):
        self.ritual.cancel()
        self.ritual.backend.close()
        self.ritual.config = self._audio_settings.config
        self.ritual.backend = create_audio_backend(self.ritual.config)

    def _palette_button(self, parent, candidate):
        button = super()._palette_button(parent, candidate)
        original = button.cget("command")

        def insert():
            # Invoke the exact original insertion callback, including template
            # text/caret/placeholder selection, before adding presentation only.
            button.tk.call(original)
            effects = self.table_grid.effects
            if effects is not None:
                if candidate.category in ("left_stick", "right_stick"):
                    self.stick_preview.pulse(0 if candidate.category == "left_stick" else 1)
                else:
                    box = self.table_grid._visible_active_box()
                    # The Entry remains above Canvas items. Emit beside its
                    # right edge so sparks are visible without covering caret.
                    effects.interaction("palette", origin=(box[2] + 5, box[1] + 8) if box else None,
                                        direction=(1.0, 0.25))
                effects.pulse_widget("palette", button, "palette")

        button.configure(command=insert)
        return button

    def _show_palette_page(self, number, *, remember=True):
        previous = getattr(self, "_palette_page", None)
        result = super()._show_palette_page(number, remember=remember)
        effects = self.table_grid.effects
        if previous is not None and previous != self._palette_page and effects is not None:
            meter = getattr(self, "hype_meter", None)
            origin = None
            if meter is not None and meter.winfo_ismapped():
                origin = (self._palette_page_label.winfo_rootx() + self._palette_page_label.winfo_width() / 2
                          - meter.winfo_rootx(), 7)
            effects.interaction("page", surface="meter", origin=origin, direction=(1, -0.15))
            effects.remove("palette")
            effects.pulse_widget("page", self._palette_page_label, "page", ink=True)
        return result

    def _intensity_changed(self):
        level = Intensity(self._motion_intensity.get())
        view = getattr(self, "ritual_view", None)
        if view is not None:
            view.level = level
            if level == Intensity.OFF:
                self.ritual.cancel()
        self.table_grid.effects.set_intensity(level)
        if view is not None:
            view.repaint()
        self.settings.update(dopagaki_intensity=level.value)

    def new_document(self):
        result = super().new_document()
        if result and getattr(self, "ritual", None) is not None:
            self.ritual.cancel()
        return result

    def open_file(self, path=None):
        result = super().open_file(path)
        if result and getattr(self, "ritual", None) is not None:
            self.ritual.cancel()
        return result

    def go_to_frame(self):
        result = super().go_to_frame()
        if result and self.table_grid.winfo_ismapped() and self.table_grid.effects is not None:
            box = self.table_grid._visible_active_box()
            self.table_grid.effects.interaction("jump", origin=(box[2] - 5, box[1] + 5) if box else None)
        return result

    def destroy(self):
        self._close_ritual()
        grid = getattr(self, "table_grid", None)
        if grid is not None:
            grid.close_effects()
        super().destroy()

    def _close_ritual(self):
        ritual, self.ritual = getattr(self, "ritual", None), None
        if ritual is not None:
            ritual.close()
        view, self.ritual_view = getattr(self, "ritual_view", None), None
        if view is not None:
            view.close()

    def _on_destroy(self, event):
        if event.widget is self:
            self._close_ritual()
            grid = getattr(self, "table_grid", None)
            if grid is not None:
                grid.close_effects()
            self._motion_intensity = None
            self._audio_enabled = None
        super()._on_destroy(event)
