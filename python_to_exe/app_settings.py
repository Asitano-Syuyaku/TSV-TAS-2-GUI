"""Non-sensitive user preferences and a shared, bounded recent-file list."""

import json
import os
import sys
import tempfile
from pathlib import Path

if __package__:
    from .converter_logic import FORMATS
    from .editor.column_layout import clean_column_widths
else:
    from converter_logic import FORMATS
    from editor.column_layout import clean_column_widths


APP_NAME = "TSV-TAS-2-GUI"
VERSION = 1
EDITOR_SIZE_DEFAULT = (1200, 700)
EDITOR_SIZE_MIN = (800, 500)
EDITOR_SIZE_MAX = (4096, 2160)


def settings_path(platform=None, environ=None, home=None):
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    variable = "APPDATA" if platform.startswith("win") else "XDG_CONFIG_HOME"
    value = environ.get(variable, "")
    if value and "\0" not in value and Path(value).is_absolute():
        directory = Path(value)
    else:
        user_home = Path.home() if home is None else Path(home)
        directory = (user_home / "AppData" / "Roaming" if platform.startswith("win")
                     else user_home / ".config")
    return directory / APP_NAME / "settings.json"


def _path(value, relative=False):
    """Normalize lexically; never stat recent paths just to load settings."""
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        return ""
    try:
        path = Path(value).expanduser()
        if not relative and not path.is_absolute():
            return ""
        return os.path.abspath(path)
    except (OSError, RuntimeError, ValueError):
        return ""


def _clean(values):
    defaults = dict(version=VERSION, recent_files=[], output_format="binary",
                    debug_enabled=False, last_input_directory="", last_output_directory="",
                    editor_width=EDITOR_SIZE_DEFAULT[0], editor_height=EDITOR_SIZE_DEFAULT[1],
                    editor_view="raw", editor_palette_page=0, editor_column_widths={},
                    dopagaki_intensity="MID")
    if (not isinstance(values, dict) or type(values.get("version")) is not int
            or values["version"] != VERSION):
        return defaults
    if values.get("output_format") in FORMATS:
        defaults["output_format"] = values["output_format"]
    if type(values.get("debug_enabled")) is bool:
        defaults["debug_enabled"] = values["debug_enabled"]
    for key in ("last_input_directory", "last_output_directory"):
        defaults[key] = _path(values.get(key))
    for key, low, high in zip(("editor_width", "editor_height"),
                              EDITOR_SIZE_MIN, EDITOR_SIZE_MAX):
        value = values.get(key)
        if type(value) is int and low <= value <= high:
            defaults[key] = value
    if values.get("editor_view") in ("raw", "table"):
        defaults["editor_view"] = values["editor_view"]
    if values.get("dopagaki_intensity") in ("OFF", "LOW", "MID", "FULL"):
        defaults["dopagaki_intensity"] = values["dopagaki_intensity"]
    page = values.get("editor_palette_page")
    if type(page) is int and page in (0, 1):
        defaults["editor_palette_page"] = page
    defaults["editor_column_widths"] = clean_column_widths(values.get("editor_column_widths"))
    recent = values.get("recent_files")
    if isinstance(recent, list):
        seen = set()
        for value in recent:
            path = _path(value)
            identity = os.path.normcase(path)
            if (path and Path(path).suffix.lower() in (".tsv", ".txt") and identity not in seen):
                defaults["recent_files"].append(path)
                seen.add(identity)
                if len(defaults["recent_files"]) == 10:
                    break
    return defaults


class AppSettings:
    def __init__(self, path=None):
        try:
            self.path = Path(path) if path is not None else settings_path()
            with self.path.open("r", encoding="utf-8") as file:
                values = json.load(file)
        except (OSError, ValueError, RuntimeError):
            # No usable home directory or read access: keep defaults in memory.
            if not hasattr(self, "path"):
                self.path = None
            values = {}
        self._values = _clean(values)

    def get(self, key, default=None):
        value = self._values.get(key, default)
        return value.copy() if isinstance(value, (list, dict)) else value

    @property
    def recent_files(self):
        return tuple(self._values["recent_files"])

    def update(self, *, persist=True, **values):
        cleaned = _clean({**self._values, **values, "version": VERSION})
        if cleaned == self._values:
            return False
        self._values = cleaned
        if persist:
            self.save()
        return True

    def add_recent(self, path):
        path = _path(str(path), relative=True)
        if not path or Path(path).suffix.lower() not in (".tsv", ".txt"):
            return
        identity = os.path.normcase(path)
        recent = [item for item in self.recent_files if os.path.normcase(item) != identity]
        self.update(recent_files=([path] + recent)[:10], last_input_directory=str(Path(path).parent))

    def remove_recent(self, path):
        identity = os.path.normcase(_path(str(path), relative=True))
        self.update(recent_files=[item for item in self.recent_files
                                  if os.path.normcase(item) != identity])

    def clear_recent(self):
        self.update(recent_files=[])

    def dialog_options(self, key):
        path = self.get(key, "")
        try:
            if path and Path(path).is_dir():
                return {"initialdir": path}
        except OSError:
            pass
        return {}

    def save(self):
        if self.path is None:
            return False
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".settings-", dir=self.path.parent)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as file:
                json.dump(_clean(self._values), file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            return True
        except (OSError, ValueError):
            return False
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
