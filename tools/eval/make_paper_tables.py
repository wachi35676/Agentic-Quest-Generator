"""Generate paper-ready Markdown / LaTeX tables from results.

Reads tools/eval/results/{headline,summary_per_profile,results}.json and
writes:

  tools/eval/results/headline_table.md   — pretty markdown for the README
  tools/eval/results/headline_table.tex  — LaTeX (booktabs) for the paper
  tools/eval/results/per_profile_table.md
  tools/eval/results/per_profile_table.tex

Run AFTER tools/eval/runner.py.

    python tools/eval/make_paper_tables.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).parent
RESULTS = HERE / "results"


def fmt_num(v: float | None, places: int = 3) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{places}f}"
    return str(v)


def fmt_ci(ci: list | None, places: int = 3) -> str:
    if not ci:
        return "—"
    return f"[{ci[0]:.{places}f}, {ci[1]:.{places}f}]"


def headline_md(headline: dict) -> str:
    lines = [
        "| Metric | n | Mean | Median | Stdev | 95% bootstrap CI |",
        "|---|---|---|---|---|---|",
    ]
    n_total = headline.get("n_sessions_total", 0)
    for label, stats in headline.items():
        if not isinstance(stats, dict):
            continue
        lines.append(
            f"| {label} | {stats['n']} | {fmt_num(stats['mean'])} | "
            f"{fmt_num(stats.get('median'))} | {fmt_num(stats.get('stdev'))} | "
            f"{fmt_ci(stats.get('ci95'))} |"
        )
    return f"_Total sessions: {n_total}_\n\n" + "\n".join(lines)


def headline_tex(headline: dict) -> str:
    lines = [
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        "Metric & $n$ & Mean & Median & Stdev & 95\\% CI \\\\",
        "\\midrule",
    ]
    for label, stats in headline.items():
        if not isinstance(stats, dict):
            continue
        ci = stats.get("ci95")
        ci_str = (f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "---")
        # Escape underscores for LaTeX.
        label_tex = label.replace("_", r"\_")
        lines.append(
            f"{label_tex} & {stats['n']} & {fmt_num(stats['mean'])} & "
            f"{fmt_num(stats.get('median'))} & {fmt_num(stats.get('stdev'))} & "
            f"{ci_str} \\\\"
        )
    lines += [
        "\\bottomrule",
        "\\end{tabular}",
    ]
    return "\n".join(lines)


def per_profile_md(per_profile: dict) -> str:
    """Emit the headline metrics per profile, rows = profiles, cols = metrics."""
    cols = [
        ("structural_pass_rate_mean",        "M1 schema-pass"),
        ("strings_accuracy_mean",            "M2 string acc"),
        ("adaptation_attempts_mean",         "M3 attempts/session"),
        ("adaptation_success_ratio_mean",    "M3 success ratio"),
        ("memory_consistency_mean",          "M4 memory cons."),
        ("latency_median_ms_mean",           "M5 median latency (ms)"),
    ]
    header = ["Profile", "n"] + [c[1] for c in cols]
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for profile, stats in per_profile.items():
        row = [profile, str(stats.get("n_sessions", 0))]
        for key, _ in cols:
            row.append(fmt_num(stats.get(key)))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def per_profile_tex(per_profile: dict) -> str:
    cols = [
        ("structural_pass_rate_mean",        "M1 schema-pass"),
        ("strings_accuracy_mean",            "M2 string acc"),
        ("adaptation_attempts_mean",         "M3 attempts"),
        ("adaptation_success_ratio_mean",    "M3 success ratio"),
        ("memory_consistency_mean",          "M4 mem. cons."),
        ("latency_median_ms_mean",           "M5 latency (ms)"),
    ]
    lines = ["\\begin{tabular}{l" + "r" * (1 + len(cols)) + "}", "\\toprule"]
    lines.append("Profile & $n$ & " + " & ".join(c[1] for c in cols) + " \\\\")
    lines.append("\\midrule")
    for profile, stats in per_profile.items():
        cells = [profile, str(stats.get("n_sessions", 0))]
        for key, _ in cols:
            cells.append(fmt_num(stats.get(key)))
        lines.append(" & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines)


def main() -> int:
    if not RESULTS.exists():
        print(f"ERROR: {RESULTS} not found. Run runner.py first.", file=sys.stderr)
        return 2
    headline_path = RESULTS / "headline.json"
    per_profile_path = RESULTS / "summary_per_profile.json"
    if not headline_path.exists() or not per_profile_path.exists():
        print(f"ERROR: missing {headline_path} or {per_profile_path}; "
              f"re-run runner.py.", file=sys.stderr)
        return 2

    headline = json.loads(headline_path.read_text())
    per_profile = json.loads(per_profile_path.read_text())

    (RESULTS / "headline_table.md").write_text(headline_md(headline))
    (RESULTS / "headline_table.tex").write_text(headline_tex(headline))
    (RESULTS / "per_profile_table.md").write_text(per_profile_md(per_profile))
    (RESULTS / "per_profile_table.tex").write_text(per_profile_tex(per_profile))

    print(f"Wrote 4 paper tables to {RESULTS}/")
    print()
    print("Headline (markdown):")
    print(headline_md(headline))
    print()
    print("Per-profile (markdown):")
    print(per_profile_md(per_profile))
    return 0


if __name__ == "__main__":
    sys.exit(main())
