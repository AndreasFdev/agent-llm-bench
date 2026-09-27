"""Comparison and leaderboard functionality."""

from typing import Any


def compare_runs(
    run_a: dict[str, Any],
    run_b: dict[str, Any],
) -> dict[str, Any]:
    """Compare two suite runs.

    Args:
        run_a: First run data (must include weighted_total and category_scores)
        run_b: Second run data

    Returns:
        Comparison dict with deltas per category and overall.
    """
    total_delta = run_a.get("weighted_total", 0) - run_b.get("weighted_total", 0)

    cat_a = run_a.get("category_scores", {})
    cat_b = run_b.get("category_scores", {})

    all_categories = set(cat_a.keys()) | set(cat_b.keys())
    category_deltas = {}
    for cat in all_categories:
        score_a = cat_a.get(cat, 0)
        score_b = cat_b.get(cat, 0)
        category_deltas[cat] = {
            "run_a": score_a,
            "run_b": score_b,
            "delta": score_a - score_b,
        }

    return {
        "overall_delta": total_delta,
        "category_deltas": category_deltas,
        "winner": "run_a" if total_delta > 0 else ("run_b" if total_delta < 0 else "tie"),
    }


def leaderboard_entry(suite_run: dict[str, Any], scores: dict[str, Any]) -> dict[str, Any]:
    """Create a leaderboard entry from a suite run and its scores.

    Args:
        suite_run: Suite run data (suite_run_id, model_name, node_id, etc.)
        scores: Score calculation result

    Returns:
        Leaderboard entry dict.
    """
    return {
        "suite_run_id": suite_run.get("suite_run_id"),
        "model_name": suite_run.get("model_name"),
        "node_id": suite_run.get("node_id"),
        "profile_name": suite_run.get("profile_name"),
        "weighted_total": scores.get("weighted_total", 0),
        "category_scores": scores.get("category_scores", {}),
        "status": suite_run.get("status"),
        "completed_at": suite_run.get("completed_at"),
    }


def rank_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank leaderboard entries by weighted total (descending).

    Args:
        entries: List of leaderboard entry dicts

    Returns:
        Ranked list with 'rank' field added.
    """
    sorted_entries = sorted(
        entries,
        key=lambda e: e.get("weighted_total", 0),
        reverse=True,
    )
    ranked = []
    for i, entry in enumerate(sorted_entries, start=1):
        ranked_entry = dict(entry)
        ranked_entry["rank"] = i
        ranked.append(ranked_entry)
    return ranked
