"""Editor hints for syntax present in the bundled converter; never validation."""

import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Candidate:
    category: str
    label: str
    text: str
    select: Optional[Tuple[int, int]] = None
    short_label: Optional[str] = None
    icon_key: Optional[str] = None

    @property
    def display_label(self):
        return self.label


_BUTTON_ICONS = {
    "a": ("A", "button_a"), "b": ("B", "button_b"),
    "x": ("X", "button_x"), "y": ("Y", "button_y"),
    "l": ("L", "button_l"), "r": ("R", "button_r"),
    "zl": ("ZL", "button_zl"), "zr": ("ZR", "button_zr"),
    "dp-u": ("Up", "dpad_up"), "dp-d": ("Down", "dpad_down"),
    "dp-l": ("Left", "dpad_left"), "dp-r": ("Right", "dpad_right"),
    "ls": ("LS", "stick_left_click"), "rs": ("RS", "stick_right_click"),
}


def _button(name, category="buttons"):
    short_label, icon_key = (_BUTTON_ICONS.get(name, (None, None))
                             if category == "buttons" else (None, None))
    return Candidate(category, name, name, short_label=short_label, icon_key=icon_key)


def _template(category, label, text, placeholder="0"):
    start = text.index(placeholder)
    return Candidate(category, label, text, (start, start + len(placeholder)))


# Keep this list tied to tsv-tas.py's getButtonBin, addToFrameRange and STAS
# command writer. Names shown here are suggestions, not a grammar definition.
CANDIDATES = (
    *(_button(name) for name in
      ("a", "b", "x", "y", "l", "r", "zl", "zr", "plus", "minus",
       "dp-l", "dp-u", "dp-r", "dp-d", "ls", "rs")),
    _template("left_stick", "ls(angle)", "ls(0)"),
    _template("left_stick", "ls(radius; angle)", "ls(0; 0)"),
    _template("left_stick", "lsx(x; y)", "lsx(0; 0)"),
    _template("right_stick", "rs(angle)", "rs(0)"),
    _template("right_stick", "rs(radius; angle)", "rs(0; 0)"),
    _template("right_stick", "rsx(x; y)", "rsx(0; 0)"),
    _template("accel", "la(x; y; z)", "la(0; 0; 0)"),
    _template("accel", "ra(x; y; z)", "ra(0; 0; 0)"),
    _template("gyro", "lg(pitch; yaw; roll)", "lg(0; 0; 0)"),
    _template("gyro", "rg(pitch; yaw; roll)", "rg(0; 0; 0)"),
    *(_button(name, "cappy") for name in ("ca", "cb", "cx", "cy")),
    _template("cappy", "cls(angle)", "cls(0)"),
    _template("cappy", "crs(angle)", "crs(0)"),
    _template("commands", "/tp x y z", "/tp 0 0 0"),
    _template("commands", "/ctp x y z", "/ctp 0 0 0"),
    _template("commands", "/absStick on", "/absStick on", "on"),
    _template("commands", "/speed 2", "/speed 2", "2"),
    Candidate("commands", "/pause", "/pause"),
    _template("commands", "/loadFile 1", "/loadFile 1", "1"),
    Candidate("commands", "/reloadFile", "/reloadFile"),
    _template("commands", "/demo on", "/demo on", "on"),
    Candidate("notation", "// comment", "// "),
    Candidate("notation", "$name = value", "$name = "),
    Candidate("notation", "a/b (loop)", "a/b"),
    Candidate("notation", "a|b (sequence)", "a|b"),
    Candidate("notation", "ls(0)->ls(90)", "ls(0)->ls(90)"),
    Candidate("notation", "[2]a (local duration)", "[2]a"),
)

PALETTE_CATEGORIES = ("buttons", "left_stick", "right_stick", "commands")
_FRAGMENT = re.compile(r"(?:/[A-Za-z]*|\$[A-Za-z_]*|[A-Za-z][A-Za-z0-9_-]*)$")
_DURATION = re.compile(r"\s*(?:\d+(?:\.\d+)?|\$[A-Za-z_][A-Za-z0-9_]*)\s*$")
_FUNCTION_NAMES = sorted({item.text.split("(", 1)[0] for item in CANDIDATES
                          if item.category in ("left_stick", "right_stick", "accel",
                                               "gyro", "cappy") and "(" in item.text},
                         key=len, reverse=True)
_BUTTON_NAMES = sorted({item.text for item in CANDIDATES
                        if item.category in ("buttons", "cappy") and "(" not in item.text},
                       key=len, reverse=True)
_INPUT = re.compile(
    r"(?:^|[/|&\s>])(?:(?:" + "|".join(map(re.escape, _FUNCTION_NAMES)) +
    r")\([^)]*\)|(?:" + "|".join(map(re.escape, _BUTTON_NAMES)) +
    r"))(?=$|[/|&\s\[(-])", re.IGNORECASE)


class CompletionState:
    def __init__(self):
        self.items = ()
        self.index = 0

    @property
    def open(self):
        return bool(self.items)

    def show(self, items):
        self.items = tuple(items)
        self.index = 0

    def close(self):
        self.items = ()
        self.index = 0

    def step(self, delta):
        if self.items:
            self.index = (self.index + delta) % len(self.items)
        return self.current

    @property
    def current(self):
        return self.items[self.index] if self.items else None


def completion_span(value, caret, column):
    """Return only a prefix near the caret; slash commands start in column zero."""
    prefix = value[:caret]
    match = _FRAGMENT.search(prefix)
    if match is None:
        return None
    fragment = match.group()
    if fragment.startswith("/") and (column != 0 or prefix[:match.start()].strip()):
        return (match.start() + 1, caret, fragment[1:]) if len(fragment) > 1 else None
    return match.start(), caret, fragment


def candidates_for(value, caret, column, limit=8):
    span = completion_span(value, caret, column)
    if span is None:
        return ()
    fragment = span[2].casefold()
    if fragment.startswith("/"):
        choices = (item for item in CANDIDATES if item.category == "commands")
    elif fragment.startswith("$"):
        choices = (item for item in CANDIDATES if item.text.startswith("$"))
    else:
        choices = (item for item in CANDIDATES if item.category != "commands")
    return tuple(item for item in choices if item.text.casefold().startswith(fragment))[:limit]


def insert_template(value, start, end, candidate):
    """Pure text edit used by autocomplete and the palette."""
    updated = value[:start] + candidate.text + value[end:]
    selection = None
    if candidate.select is not None:
        selection = start + candidate.select[0], start + candidate.select[1]
    return updated, start + len(candidate.text), selection


def classify_cell(value, column):
    """Cheap visual grouping; unknown text is never reported as an error."""
    token = value.strip()
    if not token:
        return None
    if column == 0:
        if token.startswith("//"):
            return "comment"
        if token.startswith("/"):
            return "command"
        if token.startswith("$") and "=" in token:
            return "variable"
        return "duration" if _DURATION.fullmatch(value) else None
    return "input" if _INPUT.search(token) else None


def syntax_spans(line):
    """(kind, start, end) spans for one raw line, without reading other lines."""
    spans = []
    offset = 0
    for column, value in enumerate(line.split("\t")):
        kind = classify_cell(value, column)
        if kind and value:
            spans.append((kind, offset, offset + len(value)))
        offset += len(value) + 1
    return tuple(spans)
