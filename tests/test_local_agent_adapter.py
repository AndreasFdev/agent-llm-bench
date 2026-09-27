"""Tests for LocalAgentAdapter."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_llm_bench_v03.adapters.local_agent.local_agent_adapter import (
    LocalAgentAdapter,
)
from agent_llm_bench_v03.domain.models import (
    BenchmarkResult,
    BenchmarkSpec,
    RunStatus,
    SuiteRun,
)


class TestLocalAgentAdapterPrepare:
    """Test prepare phase."""

    def test_prepare_returns_spec(self):
        adapter = LocalAgentAdapter()
        suite_run = SuiteRun(
            suite_run_id="test-suite",
            model_name="test-model",
            node_id="node-2",
            profile_name="quick",
            profile_version="1.0.0",
        )
        spec = adapter.prepare(suite_run, {})

        assert isinstance(spec, BenchmarkSpec)
        assert spec.name == "local_agent_benchmark"
        assert spec.category == "agentic"
        assert len(spec.task_ids) == 17  # T1-T17
        assert spec.timeout_sec == 480

    def test_prepare_with_hop(self):
        adapter = LocalAgentAdapter(include_hop=True)
        suite_run = SuiteRun(
            suite_run_id="test-suite",
            model_name="test-model",
            node_id="node-2",
            profile_name="full",
            profile_version="1.0.0",
        )
        spec = adapter.prepare(suite_run, {})

        assert spec.command_vars["include_hop"] is True


class TestLocalAgentAdapterValidate:
    """Test validate phase."""

    def test_validate_missing_path(self):
        adapter = LocalAgentAdapter(benchmark_path=Path("/nonexistent"))
        suite_run = SuiteRun(
            suite_run_id="test-suite",
            model_name="test-model",
            node_id="node-2",
            profile_name="quick",
            profile_version="1.0.0",
        )
        spec = adapter.prepare(suite_run, {})

        with pytest.raises(ValueError, match="does not exist"):
            adapter.validate(spec)


class TestLocalAgentAdapterParse:
    """Test parse phase."""

    def test_parse_success(self):
        adapter = LocalAgentAdapter()
        spec = BenchmarkSpec(
            name="local_agent_benchmark",
            version="1.0.0",
            category="agentic",
            task_ids=["T1"],
            timeout_sec=480,
            command_vars={},
        )

        raw = {
            "status": "completed",
            "raw_results": {
                "suite_version": "1.1.0",
                "model": "test-model",
                "machine": "nexus-bench-v03",
                "run_date": "2026-09-27T12:00:00Z",
                "endpoint": "http://localhost:9292",
                "tests": [
                    {
                        "id": "T1",
                        "status": "completed",
                        "pass": True,
                        "reason": "called get_weather(city='San Francisco')",
                        "latency_ms": 5000,
                        "tool_calls": [{"name": "get_weather", "args": "{}"}],
                        "response": "The weather is sunny.",
                    },
                    {
                        "id": "T2",
                        "status": "completed",
                        "pass": False,
                        "reason": "did not call search_places",
                        "latency_ms": 3000,
                        "tool_calls": [],
                        "response": "",
                    },
                ],
            },
        }

        result = adapter.parse(raw, spec)

        assert isinstance(result, BenchmarkResult)
        assert result.benchmark_name == "local_agent_benchmark"
        assert result.benchmark_version == "1.1.0"
        assert result.status == RunStatus.PARTIAL  # 1 pass, 1 fail
        assert abs(result.raw_score - 50.0) < 0.1  # 50%
        assert len(result.task_results) == 2
        assert result.task_results[0].status == RunStatus.COMPLETED
        assert result.task_results[1].status == RunStatus.FAILED

    def test_parse_all_pass(self):
        adapter = LocalAgentAdapter()
        spec = BenchmarkSpec(
            name="local_agent_benchmark",
            version="1.0.0",
            category="agentic",
            task_ids=["T1"],
            timeout_sec=480,
            command_vars={},
        )

        raw = {
            "status": "completed",
            "raw_results": {
                "suite_version": "1.1.0",
                "model": "test-model",
                "machine": "nexus-bench-v03",
                "run_date": "2026-09-27T12:00:00Z",
                "endpoint": "http://localhost:9292",
                "tests": [
                    {
                        "id": "T1",
                        "status": "completed",
                        "pass": True,
                        "reason": "ok",
                        "latency_ms": 5000,
                        "tool_calls": [],
                        "response": "ok",
                    },
                ],
            },
        }

        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.COMPLETED
        assert abs(result.raw_score - 100.0) < 0.1

    def test_parse_all_fail(self):
        adapter = LocalAgentAdapter()
        spec = BenchmarkSpec(
            name="local_agent_benchmark",
            version="1.0.0",
            category="agentic",
            task_ids=["T1"],
            timeout_sec=480,
            command_vars={},
        )

        raw = {
            "status": "completed",
            "raw_results": {
                "suite_version": "1.1.0",
                "model": "test-model",
                "machine": "nexus-bench-v03",
                "run_date": "2026-09-27T12:00:00Z",
                "endpoint": "http://localhost:9292",
                "tests": [
                    {
                        "id": "T1",
                        "status": "completed",
                        "pass": False,
                        "reason": "failed",
                        "latency_ms": 5000,
                        "tool_calls": [],
                        "response": "",
                    },
                ],
            },
        }

        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED
        assert abs(result.raw_score - 0.0) < 0.1

    def test_parse_execution_failed(self):
        adapter = LocalAgentAdapter()
        spec = BenchmarkSpec(
            name="local_agent_benchmark",
            version="1.0.0",
            category="agentic",
            task_ids=["T1"],
            timeout_sec=480,
            command_vars={},
        )

        raw = {
            "status": "failed",
            "error": "Connection refused",
        }

        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED
        assert result.error is not None
        assert "Connection refused" in result.error["message"]

    def test_parse_human_review(self):
        """Tests with pass=None should be counted as human-review (partial)."""
        adapter = LocalAgentAdapter()
        spec = BenchmarkSpec(
            name="local_agent_benchmark",
            version="1.0.0",
            category="agentic",
            task_ids=["T1"],
            timeout_sec=480,
            command_vars={},
        )

        raw = {
            "status": "completed",
            "raw_results": {
                "suite_version": "1.1.0",
                "model": "test-model",
                "machine": "nexus-bench-v03",
                "run_date": "2026-09-27T12:00:00Z",
                "endpoint": "http://localhost:9292",
                "tests": [
                    {
                        "id": "T1",
                        "status": "completed",
                        "pass": None,  # Human review needed
                        "reason": "needs manual inspection",
                        "latency_ms": 5000,
                        "tool_calls": [],
                        "response": "ambiguous",
                    },
                ],
            },
        }

        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.PARTIAL
        assert result.task_results[0].status == RunStatus.PARTIAL


class TestLocalAgentAdapterExecute:
    """Test execute phase with mocked runner."""

    @patch("agent_llm_bench_v03.adapters.local_agent.local_agent_adapter.LocalAgentAdapter._find_results_file")
    def test_execute_success(self, mock_find):
        adapter = LocalAgentAdapter()
        spec = BenchmarkSpec(
            name="local_agent_benchmark",
            version="1.0.0",
            category="agentic",
            task_ids=["T1"],
            timeout_sec=480,
            command_vars={"benchmark_path": "/opt/nexus-cluster/bench/local-agent-benchmark"},
        )

        # Mock runner
        runner = MagicMock()
        run_result = MagicMock()
        run_result.exit_code = 0
        run_result.stdout = "Benchmark completed"
        run_result.stderr = ""
        runner.run.return_value = run_result

        # Mock results file
        mock_results = {
            "suite_version": "1.1.0",
            "model": "test-model",
            "machine": "nexus-bench-v03",
            "run_date": "2026-09-27T12:00:00Z",
            "endpoint": "http://localhost:9292",
            "tests": [],
        }

        # Create a temp results file
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(mock_results, f)
            tmp_path = Path(f.name)
        mock_find.return_value = tmp_path

        env = {
            "BENCH_BASE_URL": "http://localhost:9292",
            "BENCH_API_KEY": "test-key",
        }

        raw = adapter.execute(spec, runner, env)

        assert raw["status"] == "completed"
        assert raw["raw_results"]["suite_version"] == "1.1.0"
        runner.run.assert_called_once()

        # Verify command includes --skip-hop
        call_args = runner.run.call_args
        cmd = call_args[0][0]
        assert "--skip-hop" in cmd

        tmp_path.unlink(missing_ok=True)

    @patch("agent_llm_bench_v03.adapters.local_agent.local_agent_adapter.LocalAgentAdapter._find_results_file")
    def test_execute_no_results_file(self, mock_find):
        adapter = LocalAgentAdapter()
        spec = BenchmarkSpec(
            name="local_agent_benchmark",
            version="1.0.0",
            category="agentic",
            task_ids=["T1"],
            timeout_sec=480,
            command_vars={"benchmark_path": "/opt/nexus-cluster/bench/local-agent-benchmark"},
        )

        runner = MagicMock()
        run_result = MagicMock()
        run_result.exit_code = 0
        run_result.stdout = ""
        run_result.stderr = ""
        runner.run.return_value = run_result

        mock_find.return_value = None

        env = {
            "BENCH_BASE_URL": "http://localhost:9292",
            "BENCH_API_KEY": "test-key",
        }

        raw = adapter.execute(spec, runner, env)

        assert raw["status"] == "failed"
        assert "No results file found" in raw["error"]
