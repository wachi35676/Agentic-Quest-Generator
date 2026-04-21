"""Report generation with charts for evaluation results.

Generates CSV summaries and matplotlib charts comparing pattern
performance across all metrics.
"""

import csv
import os
import math
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for file output
import matplotlib.pyplot as plt
import numpy as np

from evaluation.statistics import friedman_test, wilcoxon_pairwise, compute_effect_sizes


def generate_report(comparison_result, output_dir: str = None):
    """Generate a full evaluation report with CSVs and charts.

    Produces:
        - raw_scores.csv — All metrics for all (task, pattern) pairs
        - aggregate_summary.csv — Mean/std per pattern per metric
        - metric_comparison.png — Bar chart per metric grouped by pattern
        - radar_chart.png — Multi-dimensional comparison
        - efficiency_comparison.png — LLM calls, time, tokens per pattern
        - convergence_plot.png — Quality vs iteration (if data available)
        - statistical_tests.csv — Friedman and pairwise test results

    Args:
        comparison_result: ComparisonResult from Comparator.run_comparison()
        output_dir: Directory to save reports. If None, uses timestamped dir.
    """
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join("evaluation", "results", f"run_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    raw_scores = comparison_result.raw_scores
    aggregate = comparison_result.aggregate

    if not raw_scores:
        print("No results to report.")
        return

    # Generate all outputs
    _save_aggregate_csv(aggregate, output_dir)
    _generate_metric_comparison_chart(aggregate, output_dir)
    _generate_radar_chart(aggregate, output_dir)
    _generate_efficiency_comparison_chart(aggregate, output_dir)
    _generate_convergence_plot(raw_scores, output_dir)
    _run_and_save_statistical_tests(raw_scores, aggregate, output_dir)

    print(f"\nReport generated in: {output_dir}")
    print("  - aggregate_summary.csv")
    print("  - metric_comparison.png")
    print("  - radar_chart.png")
    print("  - efficiency_comparison.png")
    print("  - convergence_plot.png")
    print("  - statistical_tests.csv")


def _save_aggregate_csv(aggregate: dict, output_dir: str):
    """Save aggregate statistics to CSV."""
    csv_path = os.path.join(output_dir, "aggregate_summary.csv")

    rows = []
    for pattern, metrics in aggregate.items():
        for metric, stats in metrics.items():
            rows.append({
                "pattern": pattern,
                "metric": metric,
                "mean": f"{stats['mean']:.4f}",
                "std": f"{stats['std']:.4f}",
                "min": f"{stats['min']:.4f}",
                "max": f"{stats['max']:.4f}",
                "count": stats["count"],
            })

    if rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["pattern", "metric", "mean", "std", "min", "max", "count"]
            )
            writer.writeheader()
            writer.writerows(rows)


def _generate_metric_comparison_chart(aggregate: dict, output_dir: str):
    """Bar chart comparing each metric across patterns."""
    quality_metrics = [
        "completeness_score", "structural_validity", "interconnectedness",
        "internal_consistency",
    ]
    judge_metrics = [
        "judge_narrative_coherence", "judge_dialog_quality",
        "judge_thematic_consistency", "judge_player_engagement",
        "judge_originality",
    ]
    all_metrics = quality_metrics + judge_metrics

    patterns = list(aggregate.keys())
    if not patterns:
        return

    # Filter to metrics that actually have data
    available_metrics = []
    for m in all_metrics:
        if any(m in aggregate[p] for p in patterns):
            available_metrics.append(m)

    if not available_metrics:
        return

    n_metrics = len(available_metrics)
    fig, axes = plt.subplots(
        1, n_metrics, figsize=(4 * n_metrics, 5), squeeze=False
    )
    axes = axes[0]

    colors = plt.cm.Set2(np.linspace(0, 1, len(patterns)))

    for i, metric in enumerate(available_metrics):
        ax = axes[i]
        means = []
        stds = []
        labels = []
        for p in patterns:
            if metric in aggregate[p]:
                means.append(aggregate[p][metric]["mean"])
                stds.append(aggregate[p][metric]["std"])
                labels.append(p)
            else:
                means.append(0)
                stds.append(0)
                labels.append(p)

        x = np.arange(len(labels))
        bars = ax.bar(x, means, yerr=stds, capsize=3, color=colors[:len(labels)])
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_title(metric.replace("judge_", "").replace("_", " ").title(), fontsize=9)
        ax.set_ylabel("Score")

        # Set y-axis range based on metric type
        if metric.startswith("judge_"):
            ax.set_ylim(0, 5.5)
        elif metric in quality_metrics:
            ax.set_ylim(0, 1.1)

    plt.suptitle("Metric Comparison by Pattern", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "metric_comparison.png"), dpi=150, bbox_inches="tight")
    plt.close()


def _generate_radar_chart(aggregate: dict, output_dir: str):
    """Radar/spider chart for multi-dimensional comparison."""
    # Normalize all metrics to 0-1 scale for radar chart
    radar_metrics = [
        ("completeness_score", 1.0),      # already 0-1
        ("structural_validity", 1.0),      # already 0-1
        ("interconnectedness", 1.0),       # already 0-1
        ("internal_consistency", 1.0),     # already 0-1
        ("judge_narrative_coherence", 5.0),  # 1-5 scale
        ("judge_dialog_quality", 5.0),
        ("judge_thematic_consistency", 5.0),
        ("judge_player_engagement", 5.0),
        ("judge_originality", 5.0),
    ]

    patterns = list(aggregate.keys())
    if not patterns:
        return

    # Filter to available metrics
    available = []
    for metric, scale in radar_metrics:
        if any(metric in aggregate[p] for p in patterns):
            available.append((metric, scale))

    if len(available) < 3:
        return  # Need at least 3 dimensions for a radar chart

    labels = [m.replace("judge_", "").replace("_", " ").title() for m, _ in available]
    n_metrics = len(available)

    angles = np.linspace(0, 2 * np.pi, n_metrics, endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    colors = plt.cm.Set1(np.linspace(0, 1, len(patterns)))

    for idx, pattern in enumerate(patterns):
        values = []
        for metric, scale in available:
            if metric in aggregate[pattern]:
                values.append(aggregate[pattern][metric]["mean"] / scale)
            else:
                values.append(0)
        values += values[:1]  # Close the polygon

        ax.plot(angles, values, "o-", linewidth=2, label=pattern, color=colors[idx])
        ax.fill(angles, values, alpha=0.1, color=colors[idx])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1.1)
    ax.set_title("Pattern Comparison (Normalized)", fontsize=14, pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "radar_chart.png"), dpi=150, bbox_inches="tight")
    plt.close()


def _generate_efficiency_comparison_chart(aggregate: dict, output_dir: str):
    """Bar chart comparing efficiency metrics: LLM calls, time, tokens."""
    efficiency_metrics = [
        ("generation_time_seconds", "Generation Time (s)"),
        ("llm_calls_count", "LLM Calls"),
        ("total_tokens_estimate", "Total Tokens (est.)"),
    ]

    patterns = list(aggregate.keys())
    if not patterns:
        return

    available = [(m, label) for m, label in efficiency_metrics
                 if any(m in aggregate[p] for p in patterns)]

    if not available:
        return

    fig, axes = plt.subplots(1, len(available), figsize=(5 * len(available), 5), squeeze=False)
    axes = axes[0]
    colors = plt.cm.Set2(np.linspace(0, 1, len(patterns)))

    for i, (metric, label) in enumerate(available):
        ax = axes[i]
        means = []
        stds = []
        for p in patterns:
            if metric in aggregate[p]:
                means.append(aggregate[p][metric]["mean"])
                stds.append(aggregate[p][metric]["std"])
            else:
                means.append(0)
                stds.append(0)

        x = np.arange(len(patterns))
        ax.bar(x, means, yerr=stds, capsize=3, color=colors[:len(patterns)])
        ax.set_xticks(x)
        ax.set_xticklabels(patterns, rotation=45, ha="right")
        ax.set_title(label)
        ax.set_ylabel(label)

    plt.suptitle("Efficiency Comparison by Pattern", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "efficiency_comparison.png"), dpi=150, bbox_inches="tight"
    )
    plt.close()


def _generate_convergence_plot(raw_scores: list[dict], output_dir: str):
    """Plot quality vs task index for iterative patterns.

    Shows how quality metrics trend across tasks for each pattern.
    This is most useful for iterative patterns (reflection, critic)
    where later tasks may benefit from accumulated experience.
    """
    patterns = sorted(set(r["pattern"] for r in raw_scores if r.get("generation_success")))
    if not patterns:
        return

    metric = "complexity_score"
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = plt.cm.Set1(np.linspace(0, 1, len(patterns)))

    for idx, pattern in enumerate(patterns):
        pattern_rows = [r for r in raw_scores
                        if r["pattern"] == pattern and r.get("generation_success")
                        and metric in r]
        if not pattern_rows:
            continue

        values = [r[metric] for r in pattern_rows]
        task_labels = [r["task_id"] for r in pattern_rows]
        x = range(len(values))

        ax.plot(x, values, "o-", label=pattern, color=colors[idx], markersize=6)

    ax.set_xlabel("Task Index")
    ax.set_ylabel("Complexity Score")
    ax.set_title("Quest Complexity Across Tasks by Pattern")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "convergence_plot.png"), dpi=150, bbox_inches="tight")
    plt.close()


def _run_and_save_statistical_tests(raw_scores: list[dict], aggregate: dict, output_dir: str):
    """Run statistical tests and save results."""
    test_metrics = [
        "completeness_score", "structural_validity", "complexity_score",
        "interconnectedness", "internal_consistency",
        "judge_narrative_coherence", "judge_dialog_quality",
        "judge_thematic_consistency", "judge_player_engagement",
        "judge_originality",
    ]

    successful = [r for r in raw_scores if r.get("generation_success")]
    if not successful:
        return

    patterns = sorted(set(r["pattern"] for r in successful))
    tasks = sorted(set(r["task_id"] for r in successful))

    csv_path = os.path.join(output_dir, "statistical_tests.csv")
    rows = []

    for metric in test_metrics:
        # Build scores_by_pattern with aligned task ordering
        scores_by_pattern = {}
        for pattern in patterns:
            scores = []
            for task in tasks:
                matching = [r for r in successful
                            if r["pattern"] == pattern and r["task_id"] == task
                            and metric in r and r[metric] is not None]
                if matching:
                    scores.append(float(matching[0][metric]))
            scores_by_pattern[pattern] = scores

        # Check all groups have the same length
        lengths = [len(v) for v in scores_by_pattern.values()]
        if not lengths or min(lengths) == 0:
            continue
        if len(set(lengths)) > 1:
            # Trim to shortest
            min_len = min(lengths)
            scores_by_pattern = {k: v[:min_len] for k, v in scores_by_pattern.items()}

        # Friedman test
        if len(patterns) >= 3:
            friedman_result = friedman_test(scores_by_pattern)
            rows.append({
                "metric": metric,
                "test": "Friedman",
                "comparison": "all_patterns",
                "statistic": friedman_result.get("statistic", ""),
                "p_value": friedman_result.get("p_value", ""),
                "significant": friedman_result.get("significant", ""),
                "effect_size": "",
                "interpretation": friedman_result.get("interpretation", ""),
            })

        # Pairwise Wilcoxon
        pairwise = wilcoxon_pairwise(scores_by_pattern)
        for pair_key, pair_result in pairwise.items():
            rows.append({
                "metric": metric,
                "test": "Wilcoxon",
                "comparison": pair_key,
                "statistic": pair_result.get("statistic", ""),
                "p_value": pair_result.get("p_value", ""),
                "significant": pair_result.get("significant", ""),
                "effect_size": "",
                "interpretation": pair_result.get("direction", ""),
            })

        # Effect sizes
        effects = compute_effect_sizes(scores_by_pattern)
        for pair_key, effect_result in effects.items():
            rows.append({
                "metric": metric,
                "test": "Effect Size",
                "comparison": pair_key,
                "statistic": "",
                "p_value": "",
                "significant": "",
                "effect_size": effect_result.get("effect_size", ""),
                "interpretation": f"{effect_result.get('magnitude', '')} "
                                  f"(favors: {effect_result.get('favors', '')})",
            })

    if rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["metric", "test", "comparison", "statistic",
                            "p_value", "significant", "effect_size", "interpretation"],
            )
            writer.writeheader()
            writer.writerows(rows)
