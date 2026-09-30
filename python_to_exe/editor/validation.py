"""Run the bundled converter in disposable output paths for Editor tools."""

import csv
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .debug_csv import DebugFrames, load_debug_csv
from .snapshot import ScriptSnapshot, script_workspace

if __package__ == "editor":
    from converter_logic import build_commands
else:
    from ..converter_logic import build_commands


# These are the source-row forms emitted by the current stas-dev converter.
# Python traceback lines are deliberately excluded.
_SOURCE_LINE = re.compile(r"(?:\bon line|\(line)\s+(\d+)\b")


@dataclass(frozen=True)
class Problem:
    text: str
    line: Optional[int] = None


@dataclass(frozen=True)
class ValidationResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    source_is_tsv: bool = True

    @property
    def text(self):
        if self.stderr and self.stdout:
            return self.stderr + ("" if self.stderr.endswith("\n") else "\n") + self.stdout
        return self.stderr or self.stdout

    def problems(self, line_count):
        return parse_problems(self.text, line_count if self.source_is_tsv else None)


@dataclass(frozen=True)
class AnalyzeResult:
    report: ValidationResult
    frames: Optional[DebugFrames] = None

    @property
    def success(self):
        return self.report.success and self.frames is not None


def parse_problems(message, line_count=None):
    """Keep converter text intact; attach a row only to an explicit in-range hint."""
    problems = []
    for line in message.splitlines():
        match = (_SOURCE_LINE.search(line) if line.startswith(("Error: ", "Syntax error(s) "))
                 else None)
        number = int(match.group(1)) if match else None
        if number is not None and (line_count is None or not 1 <= number <= line_count):
            number = None
        # A converted nx-TAS input has no proven row mapping to its source file.
        if line_count is None:
            number = None
        problems.append(Problem(line, number))
    return tuple(problems)


def _run_commands(commands, base_dir, runner, source_is_tsv):
    """Shared UTF-8 subprocess execution for the Editor's confirmation tools."""
    runner = runner or subprocess.run
    stdout, stderr = [], []
    for command in commands:
        try:
            result = runner(command, cwd=base_dir, capture_output=True, text=True,
                            encoding="utf-8", errors="replace",
                            # Companion scripts use locale-default file encoding in
                            # some modes. Editor buffers are always UTF-8, on Windows too.
                            env={**os.environ, "PYTHONUTF8": "1"},
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, ValueError, RuntimeError) as error:
            stderr.append(str(error))
            return ValidationResult(False, "".join(stdout), "".join(stderr),
                                    source_is_tsv)
        stdout.append(result.stdout or "")
        stderr.append(result.stderr or "")
        if result.returncode:
            return ValidationResult(False, "".join(stdout), "".join(stderr),
                                    source_is_tsv)
    return ValidationResult(True, "".join(stdout), "".join(stderr), source_is_tsv)


def _source_is_tsv(source):
    suffix = source.suffix if isinstance(source, ScriptSnapshot) else Path(source).suffix
    return suffix.lower() == ".tsv"


def validate_script(path, output_format, skip_empty=False, base_dir=None, runner=None):
    """Compile a saved path or unsaved snapshot using the normal command builder."""
    source_is_tsv = _source_is_tsv(path)
    try:
        with script_workspace(path) as (source, destination):
            commands = build_commands(source, destination, "validation", output_format,
                                      skip_empty=skip_empty, debug=False, ftp=False,
                                      base_dir=base_dir)
            return _run_commands(commands, base_dir, runner, source_is_tsv)
    except (OSError, ValueError, RuntimeError) as error:
        return ValidationResult(False, stderr=str(error), source_is_tsv=source_is_tsv)


def analyze_script(path, output_format, skip_empty=False, base_dir=None, runner=None):
    """Compile a path or snapshot with -d; read the CSV before cleanup."""
    source_is_tsv = _source_is_tsv(path)
    report = ValidationResult(False, source_is_tsv=source_is_tsv)
    try:
        with script_workspace(path) as (source, destination):
            commands = build_commands(source, destination, "analysis", output_format,
                                      skip_empty=skip_empty, debug=True, ftp=False,
                                      base_dir=base_dir)
            report = _run_commands(commands, base_dir, runner, source_is_tsv)
            if not report.success:
                return AnalyzeResult(report)
            csv_path = Path(commands[-1][-1] + "-debug.csv")
            if not csv_path.is_file():
                raise FileNotFoundError(f"Debug CSV was not generated: {csv_path.name}")
            frames = load_debug_csv(csv_path)
            return AnalyzeResult(report, frames)
    except (OSError, ValueError, RuntimeError, csv.Error) as error:
        detail = str(error)
        stderr = report.stderr + ("" if not report.stderr or report.stderr.endswith("\n")
                                  else "\n") + detail
        return AnalyzeResult(ValidationResult(False, report.stdout, stderr, source_is_tsv))
