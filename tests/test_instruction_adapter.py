"""Tests for instruction following adapter."""

import json
from unittest.mock import MagicMock, patch

import pytest

from agent_llm_bench_v03.adapters.instruction.instruction_adapter import InstructionAdapter
from agent_llm_bench_v03.domain.models import (
    BenchmarkSpec,
    RunStatus,
    SuiteRun,
)


class TestInstructionAdapterPrepare:
    """Test instruction adapter prepare phase."""

    def test_prepare_quick_profile(self):
        adapter = InstructionAdapter(profile="quick")
        suite_run = SuiteRun(suite_run_id=1, model_name="test", node_id="node-2", profile_name="quick", profile_version="1.0.0")
        config = {}

        spec = adapter.prepare(suite_run, config)

        assert isinstance(spec, BenchmarkSpec)
        assert spec.name == "instruction_following"
        assert spec.category == "instruction_following"
        assert spec.timeout_sec == 300
        assert spec.command_vars["profile"] == "quick"
        assert spec.command_vars["tasks"] == ["ifeval"]

    def test_prepare_full_profile(self):
        adapter = InstructionAdapter(profile="full")
        suite_run = SuiteRun(suite_run_id=1, model_name="test", node_id="node-2", profile_name="quick", profile_version="1.0.0")
        config = {}

        spec = adapter.prepare(suite_run, config)

        assert spec.command_vars["profile"] == "full"
        assert "ifeval" in spec.command_vars["tasks"]


class TestInstructionAdapterParse:
    """Test instruction adapter output parsing."""

    def test_parse_success_ifeval(self):
        adapter = InstructionAdapter(profile="quick")
        spec = BenchmarkSpec(
            name="instruction_following",
            version="1.0.0",
            category="instruction_following",
            task_ids=[],
            timeout_sec=300,
            command_vars={"profile": "quick", "tasks": ["ifeval"]},
        )

        # Simulate lm-eval output format
        lm_eval_json = {
            "results": {
                "ifeval": {
                    "prompt_str_match_exact,exact_match": 0.85
                }
            }
        }

        raw = {
            "task_results": {
                "ifeval": {
                    "exit_code": 0,
                    "output": json.dumps(lm_eval_json),
                    "parsed": lm_eval_json,
                }
            }
        }

        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.COMPLETED
        assert result.benchmark_name == "instruction_following"
        assert abs(result.raw_score - 85.0) < 0.1
        assert len(result.task_results) == 1
        assert result.task_results[0].status == RunStatus.COMPLETED

    def test_parse_failed_task(self):
        adapter = InstructionAdapter(profile="quick")
        spec = BenchmarkSpec(
            name="instruction_following",
            version="1.0.0",
            category="instruction_following",
            task_ids=[],
            timeout_sec=300,
            command_vars={"profile": "quick", "tasks": ["ifeval"]},
        )

        raw = {
            "task_results": {
                "ifeval": {
                    "exit_code": -1,
                    "error": "lm_eval not found",
                }
            }
        }

        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED
        assert len(result.task_results) == 1
        assert result.task_results[0].status == RunStatus.FAILED

    def test_parse_no_results(self):
        adapter = InstructionAdapter(profile="quick")
        spec = BenchmarkSpec(
            name="instruction_following",
            version="1.0.0",
            category="instruction_following",
            task_ids=[],
            timeout_sec=300,
            command_vars={"profile": "quick"},
        )

        raw = {"task_results": {}}

        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED
        assert result.error is not None


class TestInstructionAdapterExecute:
    """Test instruction adapter execution with mocked runner."""

    @patch("agent_llm_bench_v03.adapters.instruction.instruction_adapter.ProcessRunner")
    def test_execute_success(self, mock_runner_cls):
        adapter = InstructionAdapter(profile="quick")
        spec = BenchmarkSpec(
            name="instruction_following",
            version="1.0.0",
            category="instruction_following",
            task_ids=[],
            timeout_sec=300,
            command_vars={"profile": "quick", "tasks": ["ifeval"]},
        )

        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        lm_eval_json = {
            "results": {
                "ifeval": {
                    "prompt_str_match_exact,exact_match": 0.85
                }
            }
        }

        eval_result = MagicMock()
        eval_result.exit_code = 0
        eval_result.stdout = json.dumps(lm_eval_json)
        eval_result.stderr = ""

        mock_runner.run.return_value = eval_result

        env = {
            "BENCH_BASE_URL": "http://localhost:9292",
            "BENCH_API_KEY": "test-key",
        }

        raw = adapter.execute(spec, mock_runner, env)

        assert "task_results" in raw
        assert "ifeval" in raw["task_results"]
        # Should have called runner once (one task)
        assert mock_runner.run.call_count == 1


class TestInstructionAdapterValidate:
    """Test instruction adapter validation."""

    def test_validate_lm_eval_not_found(self):
        adapter = InstructionAdapter(profile="quick")
        spec = BenchmarkSpec(
            name="instruction_following",
            version="1.0.0",
            category="instruction_following",
            task_ids=[],
            timeout_sec=300,
            command_vars={"profile": "quick"},
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("lm_eval not found")
            with pytest.raises(ValueError) as exc_info:
                adapter.validate(spec)
            assert "lm_eval" in str(exc_info.value).lower()
