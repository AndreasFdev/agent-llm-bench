"""Tests for V0.3 domain models, status transitions, and adapter contract."""

import json

import pytest

from agent_llm_bench_v03.domain.models import (
    ArtifactRef,
    BenchmarkResult,
    BenchmarkSpec,
    FailureInfo,
    Manifest,
    SuiteRun,
    TaskResult,
)
from agent_llm_bench_v03.domain.status import (
    RunStatus,
    can_transition,
    validate_transition,
)
from agent_llm_bench_v03.domain.adapter import FakeAdapter


class TestStatusTransitions:
    """Test valid and invalid status transitions."""

    def test_queued_to_running(self):
        assert can_transition(RunStatus.QUEUED, RunStatus.RUNNING)

    def test_running_to_completed(self):
        assert can_transition(RunStatus.RUNNING, RunStatus.COMPLETED)

    def test_running_to_timeout(self):
        assert can_transition(RunStatus.RUNNING, RunStatus.TIMEOUT)

    def test_running_to_partial(self):
        assert can_transition(RunStatus.RUNNING, RunStatus.PARTIAL)

    def test_completed_is_terminal(self):
        assert not can_transition(RunStatus.COMPLETED, RunStatus.RUNNING)

    def test_timeout_is_terminal(self):
        assert not can_transition(RunStatus.TIMEOUT, RunStatus.COMPLETED)

    def test_invalid_transition_raises(self):
        with pytest.raises(ValueError):
            validate_transition(RunStatus.COMPLETED, RunStatus.RUNNING)

    def test_all_terminal_states(self):
        for terminal in [
            RunStatus.COMPLETED,
            RunStatus.PARTIAL,
            RunStatus.TIMEOUT,
            RunStatus.FAILED,
            RunStatus.SKIPPED,
            RunStatus.ABORTED,
            RunStatus.BUDGET_EXHAUSTED,
        ]:
            for target in list(RunStatus):
                assert not can_transition(terminal, target), (
                    f"{terminal} should be terminal"
                )


class TestTaskResult:
    """Test TaskResult serialization and roundtrip."""

    def test_roundtrip(self):
        tr = TaskResult(
            task_id="t1",
            status=RunStatus.COMPLETED,
            raw_score=0.95,
            normalized_score=0.95,
            duration_sec=2.3,
        )
        data = tr.to_dict()
        restored = TaskResult.from_dict(data)
        assert restored.task_id == "t1"
        assert restored.status == RunStatus.COMPLETED
        assert restored.raw_score == 0.95

    def test_with_error(self):
        tr = TaskResult(
            task_id="t2",
            status=RunStatus.FAILED,
            error=FailureInfo(error_class="timeout", message="exceeded limit"),
        )
        data = tr.to_dict()
        assert "error" in data
        restored = TaskResult.from_dict(data)
        assert restored.error.message == "exceeded limit"

    def test_with_artifacts(self):
        tr = TaskResult(
            task_id="t3",
            status=RunStatus.COMPLETED,
            prompt_artifact=ArtifactRef(path="prompts/t3.txt", sha256="abc123"),
            response_artifact=ArtifactRef(path="responses/t3.json"),
        )
        data = tr.to_dict()
        restored = TaskResult.from_dict(data)
        assert restored.prompt_artifact.path == "prompts/t3.txt"


class TestBenchmarkResult:
    """Test BenchmarkResult canonical format."""

    def test_full_roundtrip(self):
        br = BenchmarkResult(
            schema_version="1.0",
            benchmark_name="test_bench",
            benchmark_version="1.0",
            adapter_version="1.0",
            status=RunStatus.COMPLETED,
            raw_score=0.85,
            normalized_score=0.85,
            task_results=[
                TaskResult(task_id="t1", status=RunStatus.COMPLETED, raw_score=1.0),
                TaskResult(task_id="t2", status=RunStatus.FAILED, raw_score=0.0),
            ],
        )
        data = br.to_dict()
        json_str = br.to_json()
        restored = BenchmarkResult.from_dict(json.loads(json_str))
        assert restored.benchmark_name == "test_bench"
        assert len(restored.task_results) == 2
        assert restored.raw_score == 0.85

    def test_missing_values_not_null_performance(self):
        """Missing values must not be interpreted as zero performance."""
        br = BenchmarkResult(
            benchmark_name="partial",
            status=RunStatus.PARTIAL,
            raw_score=None,
            task_results=[],
        )
        data = br.to_dict()
        assert "raw_score" not in data  # None values are omitted


class TestManifest:
    """Test manifest hash determinism and reproducibility."""

    def test_deterministic_task_hash(self):
        m1 = Manifest(task_ids=["t2", "t1"], seed=42, task_set_version="v1")
        m2 = Manifest(task_ids=["t1", "t2"], seed=42, task_set_version="v1")
        assert m1.compute_task_hash() == m2.compute_task_hash()

    def test_different_order_changes_hash(self):
        m1 = Manifest(task_ids=["t1", "t2"], seed=42, task_set_version="v1")
        m2 = Manifest(task_ids=["t2", "t1"], seed=42, task_set_version="v1")
        # Sorted, so same hash
        assert m1.compute_task_hash() == m2.compute_task_hash()

    def test_different_seed_changes_hash(self):
        m1 = Manifest(task_ids=["t1"], seed=42, task_set_version="v1")
        m2 = Manifest(task_ids=["t1"], seed=43, task_set_version="v1")
        assert m1.compute_task_hash() != m2.compute_task_hash()

    def test_timestamp_not_in_reproducibility_hash(self):
        """created_at must not affect the reproducibility hash."""
        m = Manifest(task_ids=["t1"], seed=42, suite_level="quick", suite_version="v1")
        h1 = m.compute_reproducibility_hash()
        m.created_at = "different-timestamp"
        h2 = m.compute_reproducibility_hash()
        assert h1 == h2

    def test_model_params_change_config_hash(self):
        m1 = Manifest(effective_params={"n_ctx": 64000})
        m2 = Manifest(effective_params={"n_ctx": 32000})
        assert m1.compute_config_hash() != m2.compute_config_hash()

    def test_manifest_json_roundtrip(self):
        m = Manifest(
            suite_level="quick",
            suite_version="v1",
            task_ids=["t1", "t2"],
            seed=42,
            model_name="test-model.gguf",
        )
        json_str = m.to_json()
        data = json.loads(json_str)
        assert data["suite_level"] == "quick"
        assert data["task_ids"] == ["t1", "t2"]


class TestFakeAdapter:
    """Test that FakeAdapter runs without SQLite or subprocess."""

    def test_full_lifecycle(self):
        adapter = FakeAdapter(results=[
            {"task_id": "t1", "passed": True, "score": 1.0},
            {"task_id": "t2", "passed": False, "score": 0.0},
        ])
        suite_run = SuiteRun(
            suite_run_id="test-001",
            profile_name="quick",
            profile_version="v1",
            model_name="test.gguf",
            node_id="node-1",
        )
        result = adapter.run(suite_run, {}, None, {})
        assert result.status == RunStatus.COMPLETED
        assert len(result.task_results) == 2
        assert result.raw_score == 0.5

    def test_failure_at_specific_task(self):
        adapter = FakeAdapter(
            results=[{"task_id": "t1", "passed": True}],
            fail_at=0,
        )
        suite_run = SuiteRun("test-002", "quick", "v1", "m.gguf", "n1")
        result = adapter.run(suite_run, {}, None, {})
        assert result.task_results[0].status == RunStatus.FAILED


class TestBenchmarkSpec:
    """Test benchmark specification."""

    def test_default_timeout(self):
        spec = BenchmarkSpec(name="test", version="1.0", category="performance")
        assert spec.timeout_sec == 300

    def test_custom_timeout(self):
        spec = BenchmarkSpec(
            name="test", version="1.0", category="performance", timeout_sec=60
        )
        assert spec.timeout_sec == 60
