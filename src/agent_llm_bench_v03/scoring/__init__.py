"""Scoring and comparison for V0.3."""

from .scorer import ScoreCalculator, normalize_score, compute_weighted_total
from .comparison import compare_runs, leaderboard_entry

__all__ = [
    "ScoreCalculator",
    "normalize_score",
    "compute_weighted_total",
    "compare_runs",
    "leaderboard_entry",
]
