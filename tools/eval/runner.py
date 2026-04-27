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
import sys
from pathlib import Path
from statistics import mean

from entities import load_entities
from metrics import all_metrics


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

    print()
    print("Aggregated summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print()
    print(f"Wrote results.json, results.csv, summary.json to {out_dir}/")
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


if __name__ == "__main__":
    sys.exit(main())
