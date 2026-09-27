"""Tests for scoring and comparison modules."""

import pytest

from agent_llm_bench_v03.scoring.scorer import (
    ScoreCalculator,
    compute_weighted_total,
    normalize_score,
)
from agent_llm_bench_v03.scoring.comparison import (
    compare_runs,
    leaderboard_entry,
    rank_entries,
)


class TestNormalizeScore:
    """Score normalization to 0-100 scale."""

    def test_higher_is_better_basic(self):
        # Value in middle of range
        score = normalize_score(50, 0, 100, higher_is_better=True)
        assert score == 50.0

    def test_higher_is_better_max(self):
        score = normalize_score(100, 0, 100, higher_is_better=True)
        assert score == 100.0

    def test_higher_is_better_min(self):
        score = normalize_score(0, 0, 100, higher_is_better=True)
        assert score == 0.0

    def test_lower_is_better_basic(self):
        # Lower latency is better
        score = normalize_score(50, 0, 100, higher_is_better=False)
        assert score == 50.0

    def test_lower_is_better_min_value_is_best(self):
        # Lowest latency gets highest score
        score = normalize_score(0, 0, 100, higher_is_better=False)
        assert score == 100.0

    def test_equal_min_max_returns_neutral(self):
        score = normalize_score(50, 50, 50, higher_is_better=True)
        assert score == 50.0

    def test_clamps_above_range(self):
        # Value above max should clamp to 100
        score = normalize_score(150, 0, 100, higher_is_better=True)
        assert score == 100.0

    def test_clamps_below_range(self):
        # Value below min should clamp to 0
        score = normalize_score(-10, 0, 100, higher_is_better=True)
        assert score == 0.0


class TestComputeWeightedTotal:
    """Weighted total calculation."""

    def test_equal_weights(self):
        scores = {"a": 80, "b": 60}
        weights = {"a": 1.0, "b": 1.0}
        total = compute_weighted_total(scores, weights)
        assert total == 70.0

    def test_different_weights(self):
        scores = {"a": 100, "b": 0}
        weights = {"a": 0.75, "b": 0.25}
        total = compute_weighted_total(scores, weights)
        assert total == 75.0

    def test_missing_weight_defaults_to_zero(self):
        scores = {"a": 80, "b": 60}
        weights = {"a": 1.0}  # b has no weight
        total = compute_weighted_total(scores, weights)
        assert total == 80.0

    def test_empty_scores(self):
        total = compute_weighted_total({}, {"a": 1.0})
        assert total == 0.0


class TestScoreCalculator:
    """ScoreCalculator class."""

    def test_calculate_basic(self):
        calc = ScoreCalculator()
        results = [
            {
                "benchmark_name": "llama_benchy",
                "category": "performance",
                "normalized_score": 80.0,
                "status": "completed",
            },
            {
                "benchmark_name": "ttft",
                "category": "performance",
                "normalized_score": 60.0,
                "status": "completed",
            },
        ]
        scores = calc.calculate(results)
        # Performance category average: (80 + 60) / 2 = 70
        assert scores["category_scores"]["performance"] == 70.0
        assert scores["result_count"] == 2

    def test_calculate_skips_failed(self):
        calc = ScoreCalculator()
        results = [
            {
                "benchmark_name": "test1",
                "category": "performance",
                "normalized_score": 80.0,
                "status": "completed",
            },
            {
                "benchmark_name": "test2",
                "category": "performance",
                "normalized_score": 60.0,
                "status": "failed",
            },
        ]
        scores = calc.calculate(results)
        # Only completed results count
        assert scores["category_scores"]["performance"] == 80.0

    def test_calculate_multiple_categories(self):
        calc = ScoreCalculator()
        results = [
            {
                "benchmark_name": "llama_benchy",
                "category": "performance",
                "normalized_score": 80.0,
                "status": "completed",
            },
            {
                "benchmark_name": "local_agent",
                "category": "agentic",
                "normalized_score": 60.0,
                "status": "completed",
            },
        ]
        scores = calc.calculate(results)
        assert scores["category_scores"]["performance"] == 80.0
        assert scores["category_scores"]["agentic"] == 60.0
        # Weighted total with default weights (performance: 0.25, agentic: 0.25)
        # Both have equal weight, so average = 70
        assert scores["weighted_total"] == 70.0

    def test_custom_weights(self):
        calc = ScoreCalculator(weights={"performance": 1.0, "agentic": 0.0})
        results = [
            {
                "benchmark_name": "llama_benchy",
                "category": "performance",
                "normalized_score": 80.0,
                "status": "completed",
            },
            {
                "benchmark_name": "local_agent",
                "category": "agentic",
                "normalized_score": 60.0,
                "status": "completed",
            },
        ]
        scores = calc.calculate(results)
        # Only performance counts (weight 1.0), agentic weight is 0
        assert scores["weighted_total"] == 80.0


class TestCompareRuns:
    """Run comparison."""

    def test_run_a_wins(self):
        run_a = {"weighted_total": 80, "category_scores": {"performance": 90}}
        run_b = {"weighted_total": 70, "category_scores": {"performance": 60}}
        result = compare_runs(run_a, run_b)
        assert result["overall_delta"] == 10
        assert result["winner"] == "run_a"

    def test_run_b_wins(self):
        run_a = {"weighted_total": 70}
        run_b = {"weighted_total": 80}
        result = compare_runs(run_a, run_b)
        assert result["overall_delta"] == -10
        assert result["winner"] == "run_b"

    def test_tie(self):
        run_a = {"weighted_total": 75}
        run_b = {"weighted_total": 75}
        result = compare_runs(run_a, run_b)
        assert result["overall_delta"] == 0
        assert result["winner"] == "tie"

    def test_category_deltas(self):
        run_a = {
            "weighted_total": 80,
            "category_scores": {"performance": 90, "agentic": 70},
        }
        run_b = {
            "weighted_total": 70,
            "category_scores": {"performance": 60, "agentic": 80},
        }
        result = compare_runs(run_a, run_b)
        assert result["category_deltas"]["performance"]["delta"] == 30
        assert result["category_deltas"]["agentic"]["delta"] == -10


class TestLeaderboardEntry:
    """Leaderboard entry creation."""

    def test_create_entry(self):
        suite_run = {
            "suite_run_id": "run-123",
            "model_name": "test-model",
            "node_id": "node-2",
            "profile_name": "quick",
            "status": "completed",
            "completed_at": "2026-09-27T12:00:00Z",
        }
        scores = {
            "weighted_total": 75.0,
            "category_scores": {"performance": 80},
        }
        entry = leaderboard_entry(suite_run, scores)
        assert entry["suite_run_id"] == "run-123"
        assert entry["model_name"] == "test-model"
        assert entry["weighted_total"] == 75.0


class TestRankEntries:
    """Leaderboard ranking."""

    def test_rank_by_score_descending(self):
        entries = [
            {"suite_run_id": "run-1", "weighted_total": 60},
            {"suite_run_id": "run-2", "weighted_total": 90},
            {"suite_run_id": "run-3", "weighted_total": 75},
        ]
        ranked = rank_entries(entries)
        assert ranked[0]["rank"] == 1
        assert ranked[0]["suite_run_id"] == "run-2"
        assert ranked[1]["rank"] == 2
        assert ranked[1]["suite_run_id"] == "run-3"
        assert ranked[2]["rank"] == 3
        assert ranked[2]["suite_run_id"] == "run-1"

    def test_empty_list(self):
        ranked = rank_entries([])
        assert ranked == []
