"""Editor-only light theme. Pure tokens/options never change global Tk styles."""


COLORS = {
    "app_background": "#f5f4f0",
    "panel_background": "#ffffff",
    "secondary_background": "#edf2f5",
    "border": "#cdd7df",
    "subtle_border": "#e0e6eb",
    "text": "#283747",
    "muted_text": "#627284",
    "accent": "#286da4",
    "accent_hover": "#205c8e",
    "selection_background": "#deecf8",
    "active_selection_outline": "#286da4",
    "success": "#397756",
    "warning": "#92671f",
    "error": "#bc3c3c",
    "palette_button": "#edf4f9",
    "palette_hover": "#dfeef8",
    "palette_text": "#2d5879",
    "header_background": "#eaf0f5",
    "header_selected": "#d9e8f4",
    "active_cell": "#e4f0fb",
    "duration_background": "#f5f8fc",
    "preview_axis": "#e0e6eb",
    "preview_circle": "#94a4b3",
    "preview_center": "#7d8e9e",
}

# Named Tk fonts inherit the OS's font choices and CJK fallback. Copies below
# adjust only size/weight, leaving the Converter's shared named fonts untouched.
FONTS = {"standard": "TkDefaultFont", "small": "TkSmallCaptionFont",
         "heading": "TkHeadingFont", "frame_info": "TkDefaultFont"}
SMALL_FONT_STEP = 1
SPACING = {"outer": 8, "section": 6, "gap": 4, "button_gap": 2,
           "toolbar_y": 4, "button_x": 7, "button_y": 2, "status_y": 2,
           "category_top": 4, "category_bottom": 1, "palette_button_y": 0,
           "palette_grid_y": 0}
# Keep the 24px icons and plots full size; trim button chrome for numeric space.
SIZES = {"palette_width": 400, "palette_row": 26, "plot_width": 160, "plot_height": 126,
         "initial_columns": 8}
TABLE_COLUMN_WIDTHS = (112, 178, 178, 99, 99, 99, 99)
LINE_WIDTHS = {"grid": 1, "header": 1, "selection": 2, "active": 2,
               "header_divider": 2}
SYNTAX_COLORS = {"comment": "#53805a", "command": "#80529e",
                 "variable": "#906326", "duration": "#295fa3",
                 "input": "#304f74"}
ROW_HINTS = {"comment": "#80a88a", "command": "#ac90bf",
             "variable": "#bda06d", "control": "#7fa4b4",
             "blank": "#d1dae2", "input": "#9bb2ca"}
TRAIL_COLORS = ("#cc2828", "#dc7777", "#e7aaaa", "#f0cece")


def editor_fonts(master):
    """Per-Editor font copies; importing the theme itself requires no Tk/display."""
    from tkinter import font

    small = font.Font(root=master, font=FONTS["small"])
    size = small.actual("size")
    small.configure(size=(1 if size >= 0 else -1) * max(8, abs(size) - SMALL_FONT_STEP))
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


def button_options(kind="toolbar", selected=False, fonts=None):
    primary = kind == "primary" or selected
    palette = kind == "palette"
    return {
        "background": COLORS["accent" if primary else
                             "palette_button" if palette else "secondary_background"],
        "foreground": COLORS["panel_background" if primary else
                             "palette_text" if palette else "text"],
        "activebackground": COLORS["accent_hover" if primary else "palette_hover"],
        "activeforeground": COLORS["panel_background" if primary else "text"],
        "disabledforeground": COLORS["muted_text"],
        "relief": "flat", "overrelief": "flat", "borderwidth": 0 if palette else 1,
        "highlightthickness": 1, "highlightbackground": COLORS["subtle_border"],
        "highlightcolor": COLORS["accent"],
        "font": (fonts or FONTS)["standard"],
        "padx": SPACING["button_x"],
        "pady": SPACING["palette_button_y" if palette else "button_y"],
    }


def entry_options():
    return {"background": COLORS["panel_background"], "foreground": COLORS["text"],
            "insertbackground": COLORS["accent"], "relief": "flat", "borderwidth": 0,
            "highlightthickness": 1, "highlightbackground": COLORS["border"],
            "highlightcolor": COLORS["accent"],
            "selectbackground": COLORS["selection_background"],
            "selectforeground": COLORS["text"]}
