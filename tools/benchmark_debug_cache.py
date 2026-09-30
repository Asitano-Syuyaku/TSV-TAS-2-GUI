"""Opt-in cache benchmark: python -m tools.benchmark_debug_cache CSV --mode sticks.

No timing assertions, dependencies, GUI, converter run, or document writes.
Use a fresh process per mode/revision for comparable RSS measurements.
"""

import argparse
import gc
import json
import statistics
import time
import tracemalloc
from pathlib import Path

from python_to_exe.editor.debug_csv import load_debug_csv, load_stick_csv


def current_rss_mib():
    """Linux current RSS, including tracing/allocator overhead; unavailable elsewhere."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 3)
    except OSError:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--mode", choices=("full", "sticks"), default="full")
    parser.add_argument("--repeat", type=int, default=3)
    options = parser.parse_args()
    if options.repeat < 1:
        parser.error("--repeat must be positive")
    load = load_stick_csv if options.mode == "sticks" else load_debug_csv
    samples = []
    for _ in range(options.repeat):
        started = time.perf_counter()
        data = load(options.csv)
        samples.append((time.perf_counter() - started) * 1000)
        del data
        gc.collect()

    tracemalloc.start(1)
    data = load(options.csv)
    current, peak = tracemalloc.get_traced_memory()
    print(json.dumps({
        "mode": options.mode,
        "rows": len(data.rows),
        "median_ms_without_tracing": round(statistics.median(samples), 3),
        "python_current_MiB": round(current / 1048576, 3),
        "python_peak_MiB": round(peak / 1048576, 3),
        "linux_current_RSS_MiB_with_tracing": current_rss_mib(),
    }, indent=2))
    tracemalloc.stop()


if __name__ == "__main__":
    main()
