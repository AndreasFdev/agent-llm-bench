"""Score normalization and weighted total calculation.

Normalization strategy:
- Performance metrics (higher is better): min-max scaling to 0-100
- Latency metrics (lower is better): inverse min-max scaling to 0-100
- Accuracy metrics: already 0-1, scale to 0-100

Weighted total combines all category scores into a single 0-100 score.
"""

from typing import Any


def normalize_score(value: float, min_val: float, max_val: float, higher_is_better: bool = True) -> float:
    """Normalize a raw score to 0-100 scale.

    Args:
        value: The raw metric value
        min_val: Minimum observed value (for scaling)
        max_val: Maximum observed value (for scaling)
        higher_is_better: If False, lower values are better (e.g. latency)

    Returns:
        Normalized score in [0, 100]
    """
    if max_val == min_val:
        return 50.0  # No range, return neutral score

    if higher_is_better:
        normalized = (value - min_val) / (max_val - min_val)
    else:
        normalized = (max_val - value) / (max_val - min_val)

    # Clamp to [0, 1]
    normalized = max(0.0, min(1.0, normalized))
    return normalized * 100.0


def compute_weighted_total(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Compute weighted total score from category scores.

    Args:
        scores: Dict of category name -> score (0-100)
        weights: Dict of category name -> weight (positive)

    Returns:
        Weighted total score in [0, 100]
    """
    total_weight = sum(weights.get(k, 0.0) for k in scores)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(
        scores[k] * weights.get(k, 0.0)
        for k in scores
    )
    return weighted_sum / total_weight


# Default category weights (can be overridden)
DEFAULT_WEIGHTS = {
    "performance": 0.25,
    "agentic": 0.25,
    "tool_calling": 0.2,
    "instruction_following": 0.2,
}


class ScoreCalculator:
    """Calculates and normalizes benchmark scores."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or DEFAULT_WEIGHTS

    def calculate(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Calculate scores from a list of benchmark results.

        Each result dict should have:
        - benchmark_name: str
        - category: str
        - raw_score: float (higher is better) or None
        - normalized_score: float (0-100) or None
        - status: str ("completed", "partial", etc.)

        Returns:
            Dict with per-category scores and weighted total.
        """
        category_scores: dict[str, list[float]] = {}

        for result in results:
            if result.get("status") not in ("completed", "partial"):
                continue
            score = result.get("normalized_score")
            if score is None:
                continue
            category = result.get("category", "unknown")
            if category not in category_scores:
                category_scores[category] = []
            category_scores[category].append(score)

        # Average scores per category
        category_averages = {}
        for category, scores in category_scores.items():
            if scores:
                category_averages[category] = sum(scores) / len(scores)

        # Compute weighted total
        total = compute_weighted_total(category_averages, self.weights)

        return {
            "category_scores": category_averages,
            "weighted_total": total,
            "weights_used": self.weights,
            "result_count": len(results),
        }
