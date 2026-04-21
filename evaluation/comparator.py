"""Batch comparison runner for evaluating all patterns on all tasks.

Runs every combination of (task x pattern), collects structural metrics
and LLM judge scores, and aggregates results for statistical analysis.
"""

import csv
import os
import time
from dataclasses import dataclass, field

from config import CONFIG
from llm.client import OllamaClient
from agents.base import GenerationTask, WorldState
from quests.schema import QuestData
from evaluation.metrics import compute_structural_metrics
from evaluation.llm_judge import evaluate_with_llm_judge


@dataclass
class ComparisonResult:
    """Results from a full comparison run."""
    raw_scores: list[dict] = field(default_factory=list)
    aggregate: dict = field(default_factory=dict)  # pattern -> metric -> {mean, std, min, max}


class Comparator:
    """Run all tasks through all patterns and collect evaluation results.

    Usage:
        comparator = Comparator(llm_client, patterns, tasks)
        result = comparator.run_comparison(output_dir="evaluation/results/run_001")
    """

    def __init__(
        self,
        llm_client: OllamaClient,
        patterns: dict,
        tasks: list[GenerationTask],
    ):
        """Initialize the comparator.

        Args:
            llm_client: OllamaClient for generation and evaluation.
            patterns: Dict of pattern_name -> PatternClass (not instances).
            tasks: List of GenerationTask instances to evaluate.
        """
        self.llm_client = llm_client
        self.patterns = patterns  # name -> class
        self.tasks = tasks

    def run_comparison(self, output_dir: str = None) -> ComparisonResult:
        """Run all tasks x all patterns, compute all metrics.

        For each combination:
            1. Generate quest using the pattern
            2. Compute structural metrics
            3. Run LLM judge evaluation
            4. Record efficiency metrics from the quest metadata

        Args:
            output_dir: Directory to save raw results CSV. If None, uses
                        a timestamped directory under eval_results_dir.

        Returns:
            ComparisonResult with raw_scores and aggregate statistics.
        """
        if output_dir is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(CONFIG.eval_results_dir, f"run_{timestamp}")
        os.makedirs(output_dir, exist_ok=True)

        result = ComparisonResult()
        world_state = WorldState(available_zones=list(CONFIG.world_zones))

        total = len(self.tasks) * len(self.patterns)
        current = 0

        for task in self.tasks:
            for pattern_name, pattern_cls in self.patterns.items():
                current += 1
                print(f"\n[{current}/{total}] Task: {task.task_id} | Pattern: {pattern_name}")
                print("-" * 50)

                row = {
                    "task_id": task.task_id,
                    "theme": task.theme,
                    "difficulty": task.difficulty,
                    "pattern": pattern_name,
                }

                # Step 1: Generate quest
                try:
                    pattern_instance = pattern_cls(llm_client=self.llm_client)
                    gen_start = time.time()
                    quest = pattern_instance.generate(task, world_state)
                    gen_duration = time.time() - gen_start
                    print(f"  Generated: {quest.title} ({gen_duration:.1f}s)")
                except Exception as e:
                    print(f"  GENERATION FAILED: {e}")
                    row["generation_error"] = str(e)
                    row["generation_success"] = False
                    result.raw_scores.append(row)
                    continue

                row["generation_success"] = True

                # Step 2: Efficiency metrics from quest metadata
                row["generation_time_seconds"] = quest.generation_duration_seconds or gen_duration
                row["llm_calls_count"] = quest.llm_calls_count
                row["total_tokens_estimate"] = quest.total_tokens_estimate

                # Step 3: Structural metrics
                try:
                    structural = compute_structural_metrics(quest)
                    row["completeness_score"] = structural["completeness_score"]
                    row["structural_validity"] = structural["structural_validity"]
                    row["complexity_score"] = structural["complexity_score"]
                    row["branching_factor"] = structural["branching_factor"]
                    row["interconnectedness"] = structural["interconnectedness"]
                    row["internal_consistency"] = structural["internal_consistency"]
                    # Flatten component counts
                    for comp_name, count in structural["component_counts"].items():
                        row[f"count_{comp_name}"] = count
                    print(f"  Structural: completeness={structural['completeness_score']:.2f}, "
                          f"validity={structural['structural_validity']:.2f}, "
                          f"complexity={structural['complexity_score']:.1f}")
                except Exception as e:
                    print(f"  STRUCTURAL METRICS FAILED: {e}")

                # Step 4: LLM judge evaluation
                try:
                    print("  Running LLM judge evaluation...")
                    judge_scores = evaluate_with_llm_judge(quest, self.llm_client)
                    for metric_name, metric_result in judge_scores.items():
                        row[f"judge_{metric_name}"] = metric_result["score"]
                        row[f"judge_{metric_name}_reasoning"] = metric_result["reasoning"]
                    scores_str = ", ".join(
                        f"{k}={v['score']:.0f}" for k, v in judge_scores.items()
                    )
                    print(f"  Judge scores: {scores_str}")
                except Exception as e:
                    print(f"  LLM JUDGE FAILED: {e}")

                # Save the generated quest
                quest_dir = os.path.join(output_dir, "quests")
                os.makedirs(quest_dir, exist_ok=True)
                quest_path = os.path.join(quest_dir, f"{task.task_id}_{pattern_name}.json")
                try:
                    quest.save(quest_path)
                except Exception:
                    pass

                result.raw_scores.append(row)

        # Compute aggregates
        result.aggregate = self._compute_aggregates(result.raw_scores)

        # Save raw scores CSV
        self._save_raw_csv(result.raw_scores, output_dir)

        print(f"\nComparison complete. Results saved to: {output_dir}")
        return result

    def _compute_aggregates(self, raw_scores: list[dict]) -> dict:
        """Compute per-pattern aggregate statistics.

        Returns:
            Dict of pattern -> metric -> {mean, std, min, max}
        """
        import statistics

        metrics_to_aggregate = [
            "completeness_score", "structural_validity", "complexity_score",
            "branching_factor", "interconnectedness", "internal_consistency",
            "generation_time_seconds", "llm_calls_count", "total_tokens_estimate",
            "judge_narrative_coherence", "judge_dialog_quality",
            "judge_thematic_consistency", "judge_player_engagement",
            "judge_originality",
        ]

        # Group by pattern
        by_pattern = {}
        for row in raw_scores:
            if not row.get("generation_success", False):
                continue
            pattern = row["pattern"]
            if pattern not in by_pattern:
                by_pattern[pattern] = []
            by_pattern[pattern].append(row)

        aggregate = {}
        for pattern, rows in by_pattern.items():
            aggregate[pattern] = {}
            for metric in metrics_to_aggregate:
                values = [r[metric] for r in rows if metric in r and r[metric] is not None]
                if not values:
                    continue
                float_values = [float(v) for v in values]
                std = statistics.stdev(float_values) if len(float_values) > 1 else 0.0
                aggregate[pattern][metric] = {
                    "mean": statistics.mean(float_values),
                    "std": std,
                    "min": min(float_values),
                    "max": max(float_values),
                    "count": len(float_values),
                }

        return aggregate

    def _save_raw_csv(self, raw_scores: list[dict], output_dir: str):
        """Save raw scores to CSV."""
        if not raw_scores:
            return

        csv_path = os.path.join(output_dir, "raw_scores.csv")

        # Collect all keys, but exclude long reasoning strings from main CSV
        all_keys = set()
        for row in raw_scores:
            all_keys.update(row.keys())

        # Separate reasoning columns
        main_keys = sorted(k for k in all_keys if not k.endswith("_reasoning"))
        reasoning_keys = sorted(k for k in all_keys if k.endswith("_reasoning"))

        # Write main CSV
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=main_keys + reasoning_keys, extrasaction="ignore")
            writer.writeheader()
            for row in raw_scores:
                writer.writerow(row)

        print(f"  Raw scores saved to: {csv_path}")
