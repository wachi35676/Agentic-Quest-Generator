"""Statistical tests for comparing agentic pattern performance.

Uses non-parametric tests appropriate for small sample sizes and
ordinal/non-normal data typical of LLM evaluation scores.
"""

import itertools
from scipy import stats


def friedman_test(scores_by_pattern: dict) -> dict:
    """Friedman test for comparing multiple related groups.

    The Friedman test is a non-parametric alternative to repeated-measures
    ANOVA, appropriate when the same tasks are evaluated across all patterns.

    Args:
        scores_by_pattern: Dict of pattern_name -> list of scores.
            All lists must be the same length (one score per task).

    Returns:
        Dict with keys:
            statistic: float — Friedman chi-squared statistic
            p_value: float — p-value
            significant: bool — True if p < 0.05
            n_groups: int — number of patterns compared
            n_observations: int — number of tasks
            interpretation: str — human-readable interpretation
    """
    pattern_names = list(scores_by_pattern.keys())
    groups = [scores_by_pattern[p] for p in pattern_names]

    # Verify all groups have the same length
    lengths = [len(g) for g in groups]
    if len(set(lengths)) > 1:
        return {
            "statistic": None,
            "p_value": None,
            "significant": False,
            "n_groups": len(pattern_names),
            "n_observations": 0,
            "interpretation": f"Groups have different lengths: {dict(zip(pattern_names, lengths))}. "
                              "Friedman test requires equal-length groups.",
            "error": True,
        }

    n_obs = lengths[0]
    if n_obs < 2:
        return {
            "statistic": None,
            "p_value": None,
            "significant": False,
            "n_groups": len(pattern_names),
            "n_observations": n_obs,
            "interpretation": "Need at least 2 observations per group for Friedman test.",
            "error": True,
        }

    if len(groups) < 3:
        return {
            "statistic": None,
            "p_value": None,
            "significant": False,
            "n_groups": len(pattern_names),
            "n_observations": n_obs,
            "interpretation": "Need at least 3 groups for Friedman test.",
            "error": True,
        }

    try:
        stat, p_value = stats.friedmanchisquare(*groups)
    except Exception as e:
        return {
            "statistic": None,
            "p_value": None,
            "significant": False,
            "n_groups": len(pattern_names),
            "n_observations": n_obs,
            "interpretation": f"Friedman test failed: {e}",
            "error": True,
        }

    significant = p_value < 0.05
    if significant:
        interpretation = (
            f"Significant difference found (chi2={stat:.3f}, p={p_value:.4f}). "
            f"At least one pattern differs significantly from the others."
        )
    else:
        interpretation = (
            f"No significant difference (chi2={stat:.3f}, p={p_value:.4f}). "
            f"Patterns perform similarly on this metric."
        )

    return {
        "statistic": float(stat),
        "p_value": float(p_value),
        "significant": significant,
        "n_groups": len(pattern_names),
        "n_observations": n_obs,
        "interpretation": interpretation,
        "error": False,
    }


def wilcoxon_pairwise(scores_by_pattern: dict) -> dict:
    """Pairwise Wilcoxon signed-rank tests between each pair of patterns.

    The Wilcoxon signed-rank test is a non-parametric test for comparing
    two related samples. It tests whether the distribution of differences
    between paired observations is symmetric around zero.

    Args:
        scores_by_pattern: Dict of pattern_name -> list of scores.
            All lists must be the same length (one score per task).

    Returns:
        Dict of "(pattern_a, pattern_b)" -> {
            statistic: float,
            p_value: float,
            significant: bool,
            direction: str — "a > b", "b > a", or "similar"
        }
    """
    pattern_names = list(scores_by_pattern.keys())
    results = {}

    for p_a, p_b in itertools.combinations(pattern_names, 2):
        scores_a = scores_by_pattern[p_a]
        scores_b = scores_by_pattern[p_b]

        if len(scores_a) != len(scores_b):
            results[f"({p_a}, {p_b})"] = {
                "statistic": None,
                "p_value": None,
                "significant": False,
                "direction": "error",
                "interpretation": "Groups have different lengths.",
                "error": True,
            }
            continue

        if len(scores_a) < 6:
            results[f"({p_a}, {p_b})"] = {
                "statistic": None,
                "p_value": None,
                "significant": False,
                "direction": "insufficient_data",
                "interpretation": f"Need at least 6 paired observations, got {len(scores_a)}.",
                "error": True,
            }
            continue

        # Check if all differences are zero
        diffs = [a - b for a, b in zip(scores_a, scores_b)]
        if all(d == 0 for d in diffs):
            results[f"({p_a}, {p_b})"] = {
                "statistic": 0.0,
                "p_value": 1.0,
                "significant": False,
                "direction": "identical",
                "interpretation": "Scores are identical for all observations.",
                "error": False,
            }
            continue

        try:
            stat, p_value = stats.wilcoxon(scores_a, scores_b)
        except Exception as e:
            results[f"({p_a}, {p_b})"] = {
                "statistic": None,
                "p_value": None,
                "significant": False,
                "direction": "error",
                "interpretation": f"Wilcoxon test failed: {e}",
                "error": True,
            }
            continue

        significant = p_value < 0.05
        mean_a = sum(scores_a) / len(scores_a)
        mean_b = sum(scores_b) / len(scores_b)

        if significant:
            direction = f"{p_a} > {p_b}" if mean_a > mean_b else f"{p_b} > {p_a}"
        else:
            direction = "similar"

        results[f"({p_a}, {p_b})"] = {
            "statistic": float(stat),
            "p_value": float(p_value),
            "significant": significant,
            "direction": direction,
            "mean_a": mean_a,
            "mean_b": mean_b,
            "error": False,
        }

    return results


def compute_effect_sizes(scores_by_pattern: dict) -> dict:
    """Compute effect sizes for all pairwise comparisons.

    Uses rank-biserial correlation as the effect size measure for
    Wilcoxon signed-rank tests. This is the recommended effect size
    for non-parametric paired comparisons.

    Effect size interpretation (|r|):
        < 0.1: negligible
        0.1-0.3: small
        0.3-0.5: medium
        > 0.5: large

    Args:
        scores_by_pattern: Dict of pattern_name -> list of scores.

    Returns:
        Dict of "(pattern_a, pattern_b)" -> {
            effect_size: float (rank-biserial r, -1 to 1),
            magnitude: str ("negligible", "small", "medium", "large"),
            favors: str (pattern name or "neither")
        }
    """
    pattern_names = list(scores_by_pattern.keys())
    results = {}

    for p_a, p_b in itertools.combinations(pattern_names, 2):
        scores_a = scores_by_pattern[p_a]
        scores_b = scores_by_pattern[p_b]

        if len(scores_a) != len(scores_b) or len(scores_a) < 2:
            results[f"({p_a}, {p_b})"] = {
                "effect_size": None,
                "magnitude": "error",
                "favors": "error",
            }
            continue

        diffs = [a - b for a, b in zip(scores_a, scores_b)]

        # Remove zero differences for rank-biserial
        nonzero_diffs = [d for d in diffs if d != 0]
        if not nonzero_diffs:
            results[f"({p_a}, {p_b})"] = {
                "effect_size": 0.0,
                "magnitude": "negligible",
                "favors": "neither",
            }
            continue

        n = len(nonzero_diffs)

        # Compute rank-biserial correlation
        # r = (sum of positive ranks - sum of negative ranks) / total sum of ranks
        abs_diffs = [abs(d) for d in nonzero_diffs]
        # Simple ranking (no ties handling for simplicity)
        ranked = sorted(range(n), key=lambda i: abs_diffs[i])
        ranks = [0.0] * n
        for rank_pos, idx in enumerate(ranked, 1):
            ranks[idx] = float(rank_pos)

        pos_rank_sum = sum(r for r, d in zip(ranks, nonzero_diffs) if d > 0)
        neg_rank_sum = sum(r for r, d in zip(ranks, nonzero_diffs) if d < 0)
        total_rank_sum = pos_rank_sum + neg_rank_sum

        if total_rank_sum == 0:
            r = 0.0
        else:
            r = (pos_rank_sum - neg_rank_sum) / total_rank_sum

        abs_r = abs(r)
        if abs_r < 0.1:
            magnitude = "negligible"
        elif abs_r < 0.3:
            magnitude = "small"
        elif abs_r < 0.5:
            magnitude = "medium"
        else:
            magnitude = "large"

        if abs_r < 0.1:
            favors = "neither"
        elif r > 0:
            favors = p_a
        else:
            favors = p_b

        results[f"({p_a}, {p_b})"] = {
            "effect_size": float(r),
            "magnitude": magnitude,
            "favors": favors,
        }

    return results
