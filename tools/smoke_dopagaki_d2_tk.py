"""Opt-in JP/EN representative D2 visual/focus/cleanup workflow."""

import argparse
import json
from pathlib import Path
import tempfile

from smoke_dopagaki_d1_tk import check_session


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save the JP/EN measurements as JSON")
    parser.add_argument("--language", choices=("ja", "en", "both"), default="both")
    parser.add_argument("--intensity", choices=("LOW", "MID", "FULL"), default=None,
                        help="Initial intensity; the workflow also checks all four levels")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="dopagaki-d2-tk-") as directory:
        languages = ("ja", "en") if arguments.language == "both" else (arguments.language,)
        reports = check_session(Path(directory), progress=True, languages=languages,
                                initial_intensity=arguments.intensity)
    if arguments.output is not None:
        arguments.output.write_text(json.dumps(reports, indent=2) + "\n")
