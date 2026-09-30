"""Paths and CLI arguments shared by both GUI languages."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


FORMATS = ("binary", "stas", "nxtas")


@dataclass(frozen=True)
class ConversionOutputs:
    primary: Path
    debug_csv: Optional[Path] = None
    intermediate_tsv: Optional[Path] = None
    ftp_requested: bool = False


def conversion_outputs(input_path, output_dir, base_name, output_format, debug=False, ftp=False):
    """Compute expected paths without writing files or requiring them to exist.

    Like build_commands, resolve paths before appending literal filename suffixes.
    The command builder remains responsible for input and collision validation.
    """
    if output_format not in FORMATS:
        raise ValueError("Unknown output format")
    source = Path(input_path).resolve()
    destination = Path(output_dir).resolve()
    suffix = {"binary": "", "stas": ".stas", "nxtas": ".txt"}[output_format]
    primary = destination / (base_name + suffix)
    return ConversionOutputs(
        primary=primary,
        debug_csv=Path(str(primary) + "-debug.csv") if debug else None,
        intermediate_tsv=destination / (base_name + ".tsv") if source.suffix.lower() == ".txt" else None,
        ftp_requested=bool(ftp),
    )


def open_output_folder(directory):
    """Ask the native file manager to open an existing folder, without a shell."""
    if not directory:
        raise ValueError("Output directory is required")
    folder = Path(directory).resolve()
    if not folder.is_dir():
        raise ValueError("Output directory does not exist")
    if sys.platform.startswith("win"):
        os.startfile(str(folder))
    else:
        command = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([command, str(folder)], check=True, capture_output=True,
                       text=True, errors="replace", timeout=10)


def scripts_dir(gui_file=None):
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(gui_file or __file__).resolve().parent.parent


def python_command():
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    # sys.executable is the GUI executable in a PyInstaller build.
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            return [launcher, "-3"]
    for name in ("python", "python3"):
        interpreter = shutil.which(name)
        if interpreter and Path(interpreter).resolve() != Path(sys.executable).resolve():
            return [interpreter]
    raise RuntimeError("Python 3 is required to run the companion converter scripts.")


def build_commands(input_path, output_dir, base_name, output_format,
                   skip_empty=False, debug=False, ftp=False,
                   base_dir=None, interpreter=None, line_map=False):
    if output_format not in FORMATS:
        raise ValueError("Unknown output format")
    if not input_path or not output_dir or not base_name:
        raise ValueError("Input file, output directory and output name are required")
    if base_name in (".", "..") or Path(base_name).name != base_name or "\\" in base_name:
        raise ValueError("Output name must be a file name without a directory")
    source = Path(input_path).resolve()
    destination = Path(output_dir).resolve()
    if not source.is_file():
        raise ValueError("Input file does not exist")
    if not destination.is_dir():
        raise ValueError("Output directory does not exist")
    extension = source.suffix.lower()
    if extension not in (".txt", ".tsv"):
        raise ValueError("Input must be a .txt or .tsv file")
    if skip_empty and output_format != "nxtas":
        raise ValueError("Skip empty frames is available only for nx-TAS")

    base_dir = Path(base_dir or scripts_dir()).resolve()
    interpreter = list(interpreter or python_command())
    outputs = conversion_outputs(source, destination, base_name, output_format, debug, ftp)
    commands = []
    if extension == ".txt":
        tsv_path = outputs.intermediate_tsv
        if tsv_path == source:
            raise ValueError("Intermediate TSV would overwrite the input file")
        commands.append(interpreter + [str(base_dir / "nx-tas-to-tsv-tas.py"),
                                       str(source), str(tsv_path)])
    else:
        tsv_path = source

    output_path = outputs.primary
    if output_path == source:
        raise ValueError("Output file would overwrite the input file")
    options = "".join(("f" if ftp else "", "n" if output_format == "nxtas" else "",
                       "s" if output_format == "stas" else "", "e" if skip_empty else "",
                       "d" if debug else "", "m" if line_map else ""))
    command = interpreter + [str(base_dir / "tsv-tas.py")]
    if options:
        command.append("-" + options)
    command.extend((str(tsv_path), str(output_path)))
    commands.append(command)
    return commands


def save_ftp_config(base_dir, ip, port, user, password):
    try:
        port_number = int(port)
    except (TypeError, ValueError):
        raise ValueError("FTP port must be an integer") from None
    if not 1 <= port_number <= 65535:
        raise ValueError("FTP port must be between 1 and 65535")
    config = {"ip": ip, "port": port_number, "user": user, "passwd": password}
    with open(Path(base_dir) / "ftp_config.json", "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False)


def load_ftp_config(base_dir):
    try:
        with open(Path(base_dir) / "ftp_config.json", encoding="utf-8") as file:
            config = json.load(file)
            return config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        return {}
