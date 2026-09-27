"""Tests for BFCL tool calling adapter."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_llm_bench_v03.adapters.tool_calling.bfcl_adapter import BfclAdapter
from agent_llm_bench_v03.domain.models import (
    BenchmarkSpec,
    RunStatus,
    SuiteRun,
)


class TestBfclAdapterPrepare:
    """Test BFCL adapter prepare phase."""

    def test_prepare_quick_profile(self):
        adapter = BfclAdapter(profile="quick")
        suite_run = SuiteRun(suite_run_id=1, model_name="test", node_id="node-2", profile_name="quick", profile_version="1.0.0")
        config = {}

        spec = adapter.prepare(suite_run, config)

        assert isinstance(spec, BenchmarkSpec)
        assert spec.name == "bfcl_tool_calling"
        assert spec.category == "tool_calling"
        assert spec.timeout_sec == 300
        assert spec.command_vars["profile"] == "quick"

    def test_prepare_full_profile(self):
        adapter = BfclAdapter(profile="full")
        suite_run = SuiteRun(suite_run_id=1, model_name="test", node_id="node-2", profile_name="quick", profile_version="1.0.0")
        config = {}

        spec = adapter.prepare(suite_run, config)

        assert spec.command_vars["profile"] == "full"
        # Full should have more categories than quick
        assert len(spec.command_vars["categories"]) >= 2


class TestBfclAdapterParse:
    """Test BFCL output parsing."""

    def test_parse_success(self):
        adapter = BfclAdapter(profile="quick")
        spec = BenchmarkSpec(
            name="bfcl_tool_calling",
            version="1.0.0",
            category="tool_calling",
            task_ids=[],
            timeout_sec=300,
            command_vars={"profile": "quick", "categories": ["simple_python"]},
        )

        raw = {
            "raw_output": (
                "simple_python accuracy: 0.85\n"
                "multiple accuracy: 0.72\n"
                "Overall: 0.785\n"
            ),
        }

        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.COMPLETED
        assert result.benchmark_name == "bfcl_tool_calling"
        # Average of 85 and 72
        expected_avg = (85.0 + 72.0) / 2
        assert abs(result.raw_score - expected_avg) < 0.1
        assert len(result.task_results) == 2

    def test_parse_failed(self):
        adapter = BfclAdapter(profile="quick")
        spec = BenchmarkSpec(
            name="bfcl_tool_calling",
            version="1.0.0",
            category="tool_calling",
            task_ids=[],
            timeout_sec=300,
            command_vars={"profile": "quick"},
        )

        raw = {"status": "failed", "error": "generate failed: connection refused"}

        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED
        assert result.error is not None
        assert "connection refused" in result.error["message"]

    def test_parse_no_scores(self):
        adapter = BfclAdapter(profile="quick")
        spec = BenchmarkSpec(
            name="bfcl_tool_calling",
            version="1.0.0",
            category="tool_calling",
            task_ids=[],
            timeout_sec=300,
            command_vars={"profile": "quick"},
        )

        raw = {"raw_output": "Some output without scores\n"}

        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED
        assert result.error["error_class"] == "parse_error"


class TestBfclAdapterExecute:
    """Test BFCL execution with mocked runner."""

    @patch("agent_llm_bench_v03.adapters.tool_calling.bfcl_adapter.ProcessRunner")
    def test_execute_success(self, mock_runner_cls):
        adapter = BfclAdapter(profile="quick")
        spec = BenchmarkSpec(
            name="bfcl_tool_calling",
            version="1.0.0",
            category="tool_calling",
            task_ids=[],
            timeout_sec=300,
            command_vars={"profile": "quick", "categories": ["simple_python"]},
        )

        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        # Mock generate success
        gen_result = MagicMock()
        gen_result.exit_code = 0
        gen_result.stdout = "Generation complete"
        gen_result.stderr = ""

        # Mock evaluate success
        eval_result = MagicMock()
        eval_result.exit_code = 0
        eval_result.stdout = "simple_python accuracy: 0.85\n"
        eval_result.stderr = ""

        mock_runner.run.side_effect = [gen_result, eval_result]

        env = {
            "BENCH_BASE_URL": "http://localhost:9292",
            "BENCH_API_KEY": "test-key",
        }

        raw = adapter.execute(spec, mock_runner, env)

        assert "raw_output" in raw
        assert "model_key" in raw
        # Should have called runner twice (generate + evaluate)
        assert mock_runner.run.call_count == 2


class TestBfclAdapterValidate:
    """Test BFCL validation."""

    def test_validate_missing_root(self):
        adapter = BfclAdapter(profile="quick", bfcl_root="/nonexistent/path")
        spec = BenchmarkSpec(
            name="bfcl_tool_calling",
            version="1.0.0",
            category="tool_calling",
            task_ids=[],
            timeout_sec=300,
            command_vars={"profile": "quick"},
        )

        with pytest.raises(ValueError) as exc_info:
            adapter.validate(spec)

        assert "BFCL root not found" in str(exc_info.value)
