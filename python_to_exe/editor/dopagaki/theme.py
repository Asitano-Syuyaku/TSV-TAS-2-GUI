"""Local dark arcade chrome with a neutral, readable editing surface."""

from functools import partial

from .. import theme as normal


COLORS = {
    **normal.COLORS,
    "app_background": "#101528",
    "panel_background": "#19233b",
    "secondary_background": "#24334e",
    "border": "#25bed7",
    "subtle_border": "#3b5272",
    "text": "#edf5ff",
    "muted_text": "#b5c6df",
    "accent": "#34d6eb",
    "accent_hover": "#67e5f3",
    "success": "#9bef80",
    "warning": "#ffdf6a",
    "error": "#ff8bca",
    "palette_button": "#293553",
    "palette_hover": "#3c496b",
    "palette_text": "#edf5ff",
    "preview_axis": "#3b5272",
    "preview_circle": "#a8bfdc",
    "preview_center": "#d4e4f6",
}
TABLE_COLORS = {
    **normal.COLORS,
    "accent": "#087caa",
    "active_selection_outline": "#087caa",
    "selection_background": "#ddf2f8",
    "active_cell": "#e8f8fc",
}
PULSE_COLORS = (TABLE_COLORS["active_selection_outline"], "#34d6eb")
COMMIT_COLORS = (TABLE_COLORS["active_selection_outline"], "#df35a0")
MICRO_COLORS = {"surface": "#28657c", "ink": "#ffdf6a", "ring": "#ff62bf"}
# LOW / MID / FULL, in seconds. Geometry/fonts stay fixed during pulses.
MICRO_DURATIONS = {"cell": (0.150, 0.180, 0.200),
                   "commit": (0.150, 0.180, 0.210),
                   "palette": (0.120, 0.160, 0.190),
                   "stick": (0.140, 0.180, 0.210),
                   "frame": (0.120, 0.170, 0.200),
                   "page": (0.120, 0.160, 0.190)}
PARTICLE_COLORS = {"light": ("#087caa", "#df35a0", "#8f61d8", "#bb7900"),
                   "dark": ("#34d6eb", "#ff62bf", "#ffdf6a", "#9bef80")}
HYPE_COLORS = ("#34d6eb", "#ff62bf", "#ffdf6a")


def blend_color(first, second, amount):
    channels = [round(int(first[index:index + 2], 16) * (1 - amount) +
                      int(second[index:index + 2], 16) * amount)
                for index in (1, 3, 5)]
    return "#" + "".join(f"{value:02x}" for value in channels)

# Reuse normal geometry, syntax colors, font copies, and style builders. These
# partials bind separate dictionaries; no global style/token mutation occurs.
button_options = partial(normal.button_options, colors=COLORS)
label_options = partial(normal.label_options, colors=COLORS)
entry_options = partial(normal.entry_options, colors=TABLE_COLORS)
table_entry_options = entry_options
