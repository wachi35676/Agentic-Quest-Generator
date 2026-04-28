"""Walks a directory of session .jsonl files, computes metrics for each,
writes a per-session JSON + an aggregated CSV.

Usage:
    python tools/eval/runner.py \
        --in tools/eval/sessions \
        --out tools/eval/results \
        --entities tools/eval/entities.json
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path
from statistics import mean, median, stdev

from entities import load_entities
from metrics import all_metrics

# Profiles must match scripts/eval_session.gd's accepted set. Used for
# per-profile breakdowns in summary_per_profile.json.
PROFILES = ("aggressive", "cautious", "explorer", "completionist")


def bootstrap_ci(values: list[float], confidence: float = 0.95,
                 n_resamples: int = 1000, seed: int = 42) -> tuple[float, float] | None:
    """Nonparametric bootstrap CI for the mean. None if too few values."""
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    means = []
    n = len(values)
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    lo = means[int(alpha * n_resamples)]
    hi = means[min(n_resamples - 1, int((1.0 - alpha) * n_resamples))]
    return (lo, hi)


def load_session(path: Path) -> list[dict]:
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"  WARN: {path.name}: skipping malformed line: {e}", file=sys.stderr)
    return out


def flatten(prefix: str, d: dict) -> dict:
    """Flatten a nested dict for CSV output."""
    out: dict = {}
    for k, v in d.items():
        key = f"{prefix}_{k}"
        if isinstance(v, dict):
            for k2, v2 in v.items():
                out[f"{key}_{k2}"] = v2
        elif isinstance(v, (list, tuple)):
            out[key] = ",".join(str(x) for x in v)
        else:
            out[key] = v
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="sessions_dir", required=True)
    parser.add_argument("--out", dest="out_dir", required=True)
    parser.add_argument("--entities", dest="entities_path", required=True)
    parser.add_argument("--profile-filter", dest="profile_filter", default=None,
                        help="Only include sessions whose id contains this string")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    entities_path = Path(args.entities_path)
    if not entities_path.exists():
        print(f"ERROR: entities.json not found at {entities_path}", file=sys.stderr)
        return 2
    entities = load_entities(entities_path)

    files = sorted(sessions_dir.glob("*.jsonl"))
    if args.profile_filter:
        files = [f for f in files if args.profile_filter in f.name]
    if not files:
        print(f"ERROR: no sessions found in {sessions_dir}", file=sys.stderr)
        return 1

    rows: list[dict] = []
    print(f"Processing {len(files)} session(s)...")
    for f in files:
        events = load_session(f)
        if not events:
            print(f"  {f.name}: empty, skipping")
            continue
        m = all_metrics(events, entities)
        row: dict = {"session": f.stem, "events": len(events)}
        for k, v in m.items():
            row.update(flatten(k, v))
        rows.append(row)
        print(f"  {f.name}: {len(events)} events, "
              f"struct_pass={m['structural'].get('pass_rate')}, "
              f"latency_med={m['latency'].get('median_ms')}")

    # Per-session JSON.
    (out_dir / "results.json").write_text(json.dumps(rows, indent=2))

    # Aggregated CSV.
    if rows:
        fields = sorted({k for r in rows for k in r.keys()})
        with (out_dir / "results.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    # Aggregated summary (means across sessions, ignoring None).
    summary = _aggregate(rows)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    # Per-profile breakdown (paper-grade tables).
    per_profile = _aggregate_per_profile(rows)
    (out_dir / "summary_per_profile.json").write_text(json.dumps(per_profile, indent=2))

    # Headline metrics block — what the paper writeup will actually quote.
    headline = _headline(rows)
    (out_dir / "headline.json").write_text(json.dumps(headline, indent=2))

    print()
    print("Headline metrics (mean across sessions, with 95% bootstrap CI):")
    for k, v in headline.items():
        print(f"  {k}: {v}")
    print()
    print(f"Wrote results.json, results.csv, summary.json, summary_per_profile.json, headline.json to {out_dir}/")
    return 0


def _aggregate(rows: list[dict]) -> dict:
    """Mean across sessions for each metric column. Skips None/null."""
    if not rows:
        return {}
    fields = sorted({k for r in rows for k in r.keys()})
    agg: dict = {}
    for f in fields:
        vals = [r[f] for r in rows if r.get(f) is not None and isinstance(r.get(f), (int, float))]
        if vals:
            agg[f"{f}_mean"] = mean(vals)
            agg[f"{f}_count"] = len(vals)
    return agg


def _aggregate_per_profile(rows: list[dict]) -> dict:
    out: dict = {}
    for prof in PROFILES:
        prof_rows = [r for r in rows if prof in r["session"]]
        if prof_rows:
            out[prof] = {"n_sessions": len(prof_rows), **_aggregate(prof_rows)}
    return out


def _headline(rows: list[dict]) -> dict:
    """The paper's headline numbers: mean + 95% bootstrap CI for each
    of the five metrics, plus session count contributing to each."""
    if not rows:
        return {}

    def vals_of(field: str) -> list[float]:
        return [r[field] for r in rows
                if r.get(field) is not None and isinstance(r.get(field), (int, float))]

    out: dict = {"n_sessions_total": len(rows)}
    headline_fields = [
        ("structural_parse_rate",        "M1: parse rate"),
        ("structural_pass_rate",         "M1: schema-pass rate"),
        ("structural_avg_attempts",      "M1: avg attempts"),
        ("structural_avg_sanitizer_fixes", "M1: avg sanitizer fixes"),
        ("strings_accuracy",             "M2: string accuracy"),
        ("adaptation_attempts",          "M3: replan attempts"),
        ("adaptation_successful_orchestrations", "M3: successful orchestrations"),
        ("adaptation_revisions",         "M3: revisions"),
        ("adaptation_success_ratio",     "M3: success ratio"),
        ("adaptation_revisions_per_hour","M3: revisions per hour"),
        ("memory_consistency",           "M4: memory consistency"),
        ("latency_median_ms",            "M5: median latency (ms)"),
        ("latency_p95_ms",               "M5: p95 latency (ms)"),
        ("latency_max_ms",               "M5: max latency (ms)"),
    ]
    for field, label in headline_fields:
        vals = vals_of(field)
        if not vals:
            out[label] = {"n": 0, "mean": None, "ci95": None}
            continue
        ci = bootstrap_ci(vals)
        out[label] = {
            "n": len(vals),
            "mean": mean(vals),
            "stdev": stdev(vals) if len(vals) >= 2 else 0.0,
            "median": median(vals),
            "ci95": list(ci) if ci else None,
        }
    return out


if __name__ == "__main__":
    sys.exit(main())
