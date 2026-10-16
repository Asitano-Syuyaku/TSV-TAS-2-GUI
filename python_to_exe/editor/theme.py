"""Editor-only Dopagaki3 "1F FEVER" neon theme (dopagaki3.md §4).

Pure tokens/options never change global Tk styles. Neon colors carry fixed
meanings: YELLOW confirmed frame data, CYAN selection/focus/LS, MAGENTA
heat/RS/send, GREEN confirmed/success, PURPLE commands, ORANGE "so close".
"""


COLORS = {
    # VOID ground, neutral data, neon only for state and reward.
    "app_background": "#07060d",
    "panel_background": "#0f0d1a",
    "secondary_background": "#1c1832",
    "cell_background": "#141124",
    "virtual_cell": "#0c0b16",
    "border": "#3a3260",
    "subtle_border": "#2a2445",
    "text": "#f2eeff",
    "muted_text": "#9a92bf",
    "header_text": "#c9c2ea",
    "on_neon": "#0b0a12",
    "accent": "#19d3f0",
    "accent_hover": "#5fe3f6",
    "selection_background": "#182c40",
    "active_selection_outline": "#19d3f0",
    "active_cell": "#10364a",
    "raw_selection": "#2c2352",
    "cursor_line": "#1a1630",
    "header_background": "#1c1832",
    "header_selected": "#2c2352",
    "duration_background": "#191530",
    "neon_yellow": "#ffe600",
    "neon_yellow_hover": "#fff27a",
    "neon_magenta": "#ff2d8a",
    "neon_magenta_hover": "#ff6aad",
    "neon_green": "#39ff14",
    "neon_purple": "#a35bff",
    "neon_orange": "#ff8a1f",
    "success": "#39ff14",
    "warning": "#ff8a1f",
    "error": "#ff5c7a",
    "palette_button": "#1c1832",
    "palette_hover": "#2c2352",
    "palette_text": "#f2eeff",
    "preview_background": "#0b0a14",
    "preview_axis": "#2a2445",
    "preview_circle": "#3a3260",
    "preview_center": "#9a92bf",
}

# Named Tk fonts inherit the OS's font choices and CJK fallback. Copies below
# adjust only size/weight, leaving the Converter's shared named fonts untouched.
FONTS = {"standard": "TkDefaultFont", "small": "TkSmallCaptionFont",
         "heading": "TkHeadingFont", "frame_info": "TkDefaultFont"}
SMALL_FONT_STEP = 1
SPACING = {"outer": 8, "section": 6, "gap": 4, "button_gap": 2,
           "toolbar_y": 4, "button_x": 7, "button_y": 2, "status_y": 2,
           "category_top": 4, "category_bottom": 1, "palette_button_y": 0,
           "palette_grid_y": 0, "deck_y": 5, "deck_group": 12, "rim": 2,
           "category_bar": 3}
# Keep the 24px icons and plots full size; trim button chrome for numeric space.
SIZES = {"palette_width": 400, "palette_row": 26, "palette_key_row": 36,
         "plot_width": 160, "plot_height": 126,
         "initial_columns": 8}
TABLE_COLUMN_WIDTHS = (112, 178, 178, 99, 99, 99, 99)
LINE_WIDTHS = {"grid": 1, "header": 1, "selection": 2, "active": 2,
               "header_divider": 2, "lockon": 2, "duration_header": 2}
# Lock-on bracket arm length on the active cell (§4.3).
LOCKON_ARM = 6
SYNTAX_COLORS = {"comment": "#7fc29b", "command": "#c69bff",
                 "variable": "#ffb547", "duration": "#ffe600",
                 "input": "#8fe9ff"}
ROW_HINTS = {"comment": "#3faf6f", "command": "#a35bff",
             "variable": "#ff8a1f", "control": "#ff2d8a",
             "blank": "#2a2445", "input": "#19d3f0"}
# Current sample first, then 1-3 frames back, sinking toward the plot ground.
STICK_RAMPS = {"ls": ("#19d3f0", "#138fa6", "#0e5f70", "#0a3a45"),
               "rs": ("#ff2d8a", "#b42263", "#771843", "#451029")}
STICK_CORE = "#ffffff"
# HEAT ramp (E 0 -> 1). Phase 1 has no heat yet, so the RIM uses the first stop.
HEAT_RAMP = ("#19d3f0", "#a35bff", "#ff2d8a", "#ff8a1f", "#ffe600")
# Palette category bars (§8.3); unknown categories use muted text.
CATEGORY_COLORS = {"buttons": "#ffe600", "left_stick": "#19d3f0",
                   "right_stick": "#ff2d8a", "commands": "#a35bff",
                   "script_info": "#a35bff", "cappy": "#39ff14", "motion": "#ff8a1f",
                   "accel": "#ff8a1f", "gyro": "#ff8a1f",
                   "notation": "#9a92bf", "stick_preview": "#9a92bf"}


# Display scale for pixel-defined geometry (HUD, palette, table defaults, FX).
# 1.0 except on DPI-aware Windows, where it is DPI / 96 (display.configure_root).
UI_SCALE = {"value": 1.0}
MIN_TEXT_POINTS = 9  # Small text never shrinks below this (readability, not density).


def set_ui_scale(value):
    UI_SCALE["value"] = max(1.0, float(value))


def px(value):
    """Scale a pixel length defined at 96 DPI to the current display."""
    return int(round(value * UI_SCALE["value"]))


def editor_fonts(master):
    """Per-Editor font copies; importing the theme itself requires no Tk/display."""
    from tkinter import font

    small = font.Font(root=master, font=FONTS["small"])
    size = small.actual("size")
    small.configure(size=(1 if size >= 0 else -1) *
                    max(MIN_TEXT_POINTS, abs(size) - SMALL_FONT_STEP))
    heading = font.Font(root=master, font=FONTS["heading"])
    # Tkinter ignores constructor style options when a source font is supplied.
    heading.configure(weight="bold")
    frame_info = font.Font(root=master, font=FONTS["frame_info"])
    frame_info.configure(weight="bold")
    return {"standard": FONTS["standard"], "small": small, "heading": heading,
            "frame_info": frame_info}


def label_options(surface="panel_background", role="standard", fonts=None):
    return {"background": COLORS[surface],
            "foreground": COLORS["muted_text" if role == "small" else "text"],
            "font": (fonts or FONTS)[role], "pady": 0}


# Neon-filled buttons carry dark text (§4.1): yellow 15.5:1, magenta 5.6:1, cyan.
_BUTTON_KINDS = {
    "toolbar": ("secondary_background", "text", "palette_hover", "text"),
    "palette": ("palette_button", "palette_text", "palette_hover", "text"),
    "primary": ("accent", "on_neon", "accent_hover", "on_neon"),
    "convert": ("neon_yellow", "on_neon", "neon_yellow_hover", "on_neon"),
    "send": ("neon_magenta", "on_neon", "neon_magenta_hover", "on_neon"),
}


def button_options(kind="toolbar", selected=False, fonts=None):
    background, foreground, active, active_text = _BUTTON_KINDS[
        "primary" if selected else kind]
    palette = kind == "palette"
    return {
        "background": COLORS[background],
        "foreground": COLORS[foreground],
        "activebackground": COLORS[active],
        "activeforeground": COLORS[active_text],
        "disabledforeground": COLORS["muted_text"],
        "relief": "flat", "overrelief": "flat", "borderwidth": 0 if palette else 1,
        "highlightthickness": 1, "highlightbackground": COLORS["subtle_border"],
        "highlightcolor": COLORS["accent"],
        "font": (fonts or FONTS)["standard"],
        "padx": SPACING["button_x"],
        "pady": SPACING["palette_button_y" if palette else "button_y"],
    }


def entry_options():
    return {"background": COLORS["cell_background"], "foreground": COLORS["text"],
            "insertbackground": COLORS["neon_yellow"], "insertwidth": 2,
            "relief": "flat", "borderwidth": 0,
            "highlightthickness": 1, "highlightbackground": COLORS["border"],
            "highlightcolor": COLORS["accent"],
            "selectbackground": COLORS["raw_selection"],
            "selectforeground": COLORS["text"]}


def listbox_options():
    """Autocomplete popup (§8.1): magenta selection with dark text."""
    return {"background": COLORS["panel_background"], "foreground": COLORS["text"],
            "selectbackground": COLORS["neon_magenta"], "selectforeground": COLORS["on_neon"],
            "highlightthickness": 1, "highlightbackground": COLORS["border"],
            "highlightcolor": COLORS["accent"], "relief": "flat", "borderwidth": 0}


def menu_options():
    """Context menus; Windows keeps native colors (§8.8)."""
    return {"background": COLORS["panel_background"], "foreground": COLORS["text"],
            "activebackground": COLORS["header_selected"], "activeforeground": COLORS["text"],
            "disabledforeground": COLORS["muted_text"], "relief": "flat", "borderwidth": 1}


def choice_options(surface="app_background"):
    """Checkbutton / Radiobutton on the dark ground (Converter, §8.7)."""
    return {"background": COLORS[surface], "foreground": COLORS["text"],
            "activebackground": COLORS[surface], "activeforeground": COLORS["accent"],
            "selectcolor": COLORS["cell_background"], "disabledforeground": COLORS["muted_text"],
            "highlightthickness": 0, "borderwidth": 0}


INSPECTOR = {"row": COLORS["cell_background"], "row_alt": "#17142a",
             "selected": COLORS["active_cell"], "grid": COLORS["subtle_border"],
             "header": COLORS["header_background"], "header_line": COLORS["border"],
             "header_text": COLORS["header_text"], "text": COLORS["text"]}
