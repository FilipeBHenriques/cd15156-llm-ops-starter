"""CLI: compute per-question descriptive statistics from a `make eval` run.

`make eval` (scripts/run_eval.py) only prints the aggregate *means* for
each RAGAS metric. The capstone rubric (Deliverable 5) requires the
regression threshold to be justified with a descriptive statistic
computed from the **per-question** scores — a median, a percentile, or
a min/max range — which the mean alone can't give you.

Usage:
    uv run python scripts/run_eval.py --output data/eval_results.json
    uv run python scripts/eval_stats.py data/eval_results.json

This reads the `rows` list that `run_eval.py --output` writes (one dict
per golden-set question, with a column per RAGAS metric) and prints,
per metric: mean, median, min, max, and the 10th/90th percentiles.
"""

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

METRICS = ["faithfulness", "answer_relevancy", "context_recall", "context_precision"]


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile, no numpy dependency required."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "results_path",
        type=Path,
        help="Path to the JSON file written by `run_eval.py --output <path>`.",
    )
    args = parser.parse_args(argv)

    if not args.results_path.exists():
        print(
            f"error: {args.results_path} not found.\n"
            f"Run `uv run python scripts/run_eval.py --output {args.results_path}` first.",
            file=sys.stderr,
        )
        return 1

    data = json.loads(args.results_path.read_text())
    rows = data.get("rows", [])
    if not rows:
        print(f"error: no per-question rows found in {args.results_path}", file=sys.stderr)
        return 1

    print(f"Per-question stats across {len(rows)} golden-set questions\n")
    print(f"{'metric':<20} {'mean':>8} {'median':>8} {'min':>8} {'p10':>8} {'p90':>8} {'max':>8}  excluded")
    for metric in METRICS:
        raw = [r[metric] for r in rows if metric in r and r[metric] is not None]
        # RAGAS writes NaN into a row's metric when that judge call failed
        # (e.g. a proxy timeout) rather than dropping the row. NaN silently
        # poisons `mean` (NaN propagates through sum) and can land anywhere
        # in a naive sort, corrupting median/percentiles too — so it must be
        # filtered out explicitly, not just checked for `is not None`.
        values = [float(v) for v in raw if not math.isnan(float(v))]
        excluded = len(raw) - len(values)
        if not values:
            continue
        print(
            f"{metric:<20} "
            f"{statistics.fmean(values):>8.3f} "
            f"{statistics.median(values):>8.3f} "
            f"{min(values):>8.3f} "
            f"{percentile(values, 10):>8.3f} "
            f"{percentile(values, 90):>8.3f} "
            f"{max(values):>8.3f}  "
            f"{excluded}/{len(raw)}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())