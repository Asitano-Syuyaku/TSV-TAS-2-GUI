"""Run the bundled converter for validation without changing the user's output."""

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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


def validate_script(path, output_format, skip_empty=False, base_dir=None, runner=None):
    """Compile into a disposable directory using the normal command builder."""
    source = Path(path)
    source_is_tsv = source.suffix.lower() == ".tsv"
    runner = runner or subprocess.run
    stdout, stderr = [], []
    try:
        with tempfile.TemporaryDirectory(prefix="tas-validation-") as destination:
            commands = build_commands(source, destination, "validation", output_format,
                                      skip_empty=skip_empty, debug=False, ftp=False,
                                      base_dir=base_dir)
            for command in commands:
                result = runner(command, cwd=base_dir, capture_output=True, text=True,
                                errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                stdout.append(result.stdout or "")
                stderr.append(result.stderr or "")
                if result.returncode:
                    return ValidationResult(False, "".join(stdout), "".join(stderr),
                                            source_is_tsv)
    except (OSError, ValueError, RuntimeError) as error:
        return ValidationResult(False, "".join(stdout), "".join(stderr) + str(error),
                                source_is_tsv)
    return ValidationResult(True, "".join(stdout), "".join(stderr), source_is_tsv)
