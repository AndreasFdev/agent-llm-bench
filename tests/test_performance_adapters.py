"""Tests for llama-benchy and TTFT performance adapters."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_llm_bench_v03.adapters.performance.llama_benchy_adapter import LlamaBenchyAdapter
from agent_llm_bench_v03.adapters.performance.ttft_adapter import TTFTAdapter
from agent_llm_bench_v03.domain.models import SuiteRun, BenchmarkSpec
from agent_llm_bench_v03.domain.status import RunStatus

FIXTURES = Path(__file__).parent / "fixtures"


class TestLlamaBenchyAdapter:
    """Test llama-benchy adapter parsing and validation."""

    @pytest.fixture
    def adapter(self):
        return LlamaBenchyAdapter(llama_benchy_dir="/tmp/fake-benchy")

    @pytest.fixture
    def suite_run(self):
        return SuiteRun(
            suite_run_id="test-001",
            profile_name="quick",
            profile_version="v1",
            model_name="test.gguf",
            node_id="inf-2",
        )

    def test_parse_valid_json(self, adapter):
        """Valid llama-benchy output produces completed result with TG throughput."""
        with open(FIXTURES / "llama_benchy_valid.json") as f:
            data = json.load(f)

        raw = {"exit_code": 0, "json": data, "output_file": "/tmp/test.json"}
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.COMPLETED
        assert result.raw_score == pytest.approx(92.90, rel=0.01)
        assert len(result.task_results) == 1
        assert result.task_results[0].status == RunStatus.COMPLETED
        assert result.metadata["tg_throughput_mean"] == pytest.approx(92.90, rel=0.01)

    def test_parse_invalid_tps_zero(self, adapter):
        """Zero throughput is rejected as invalid."""
        with open(FIXTURES / "llama_benchy_invalid_tps.json") as f:
            data = json.load(f)

        raw = {"exit_code": 0, "json": data}
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED
        assert result.error.error_class in ("invalid_metrics", "no_valid_tps")

    def test_parse_negative_tps_rejected(self, adapter):
        """Negative throughput is rejected."""
        with open(FIXTURES / "llama_benchy_nan.json") as f:
            data = json.load(f)

        raw = {"exit_code": 0, "json": data}
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED

    def test_timeout_not_stored_as_zero_tps(self, adapter):
        """Timeout produces TIMEOUT status, not 0 TPS."""
        raw = {
            "exit_code": -1,
            "timed_out": True,
            "stdout": "",
            "stderr": "",
        }
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.TIMEOUT
        assert result.raw_score is None  # Not 0

    def test_process_failure(self, adapter):
        """Non-zero exit code produces FAILED status."""
        raw = {
            "exit_code": 1,
            "stdout": "",
            "stderr": "connection refused",
        }
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED
        assert result.error.error_class == "process_failure"

    def test_quick_profile_parameters(self, adapter):
        """Quick profile uses reduced runs and warmups."""
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        assert spec.command_vars["runs"] == 2
        assert spec.command_vars["warmup"] == 1

    def test_full_profile_parameters(self, adapter):
        """Full profile uses more runs and warmups."""
        spec = adapter.prepare(self.suite_run, {"profile": "full"})
        assert spec.command_vars["runs"] == 3
        assert spec.command_vars["warmup"] == 2

    def test_validate_missing_directory(self):
        """Validation fails when llama-benchy directory doesn't exist."""
        adapter = LlamaBenchyAdapter(llama_benchy_dir="/nonexistent/path")
        with pytest.raises(ValueError, match="not found"):
            adapter.validate(BenchmarkSpec(name="test", version="1.0", category="performance"))

    def test_execute_uses_process_runner(self, adapter):
        """Execute delegates to ProcessRunner and reads output file."""
        runner = MagicMock()
        runner.run.return_value = MagicMock(
            exit_code=0, stdout="", stderr="", status="completed"
        )
        runner.remaining_budget.return_value = 300

        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        env = {
            "BENCH_BASE_URL": "http://localhost:9292/v1",
            "BENCH_API_KEY": "test-key",
            "BENCH_MODEL": "test-model",
        }

        # Mock os.path.exists to return True and mock file reading
        with patch.dict("os.environ", env), \
             patch("agent_llm_bench_v03.adapters.performance.llama_benchy_adapter.os.path.exists", return_value=True), \
             patch("builtins.open") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"benchmarks": []})
            raw = adapter.execute(spec, runner, env)

        assert raw["exit_code"] == 0
        assert "output_file" in raw
        # runner.run was called with the command string
        runner.run.assert_called_once()
        call_args = runner.run.call_args
        assert "--base-url http://localhost:9292/v1" in call_args[0][0]




class TestTTFTAdapter:
    """Test TTFT adapter."""

    @pytest.fixture
    def adapter(self):
        return TTFTAdapter(timeout_per_request=10)

    @pytest.fixture
    def suite_run(self):
        return SuiteRun(
            suite_run_id="test-002",
            profile_name="quick",
            profile_version="v1",
            model_name="test.gguf",
            node_id="inf-2",
        )

    def test_parse_valid_results(self, adapter):
        """Valid TTFT results produce completed status with mean in ms."""
        raw = {
            "results": [
                {"prompt_length": 512, "ttft_values_s": [0.5, 0.6]},
                {"prompt_length": 1024, "ttft_values_s": [0.8, 0.9]},
            ]
        }
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.COMPLETED
        # Mean of [0.5, 0.6, 0.8, 0.9] = 0.7s = 700ms
        assert result.raw_score == pytest.approx(700.0, rel=0.01)
        assert len(result.task_results) == 2

    def test_parse_filters_invalid_values(self, adapter):
        """None and negative values are filtered out."""
        raw = {
            "results": [
                {"prompt_length": 512, "ttft_values_s": [0.5, None, -1.0]},
            ]
        }
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.COMPLETED
        # Only 0.5 is valid
        assert result.task_results[0].metadata["valid_runs"] == 1

    def test_parse_all_invalid_fails(self, adapter):
        """All invalid values produce FAILED status."""
        raw = {
            "results": [
                {"prompt_length": 512, "ttft_values_s": [None, None]},
            ]
        }
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED

    def test_parse_config_error(self, adapter):
        """Missing BENCH_BASE_URL produces config error."""
        raw = {"error": "BENCH_BASE_URL not set"}
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        result = adapter.parse(raw, spec)

        assert result.status == RunStatus.FAILED
        assert result.error.error_class == "config_error"

    def test_quick_profile_parameters(self, adapter):
        """Quick profile uses 2 prompt lengths and 2 runs."""
        spec = adapter.prepare(self.suite_run, {"profile": "quick"})
        assert spec.command_vars["lengths"] == [512, 1024]
        assert spec.command_vars["runs"] == 2

    def test_full_profile_parameters(self, adapter):
        """Full profile uses 3 prompt lengths and 3 runs."""
        spec = adapter.prepare(self.suite_run, {"profile": "full"})
        assert spec.command_vars["lengths"] == [512, 1024, 2048]
        assert spec.command_vars["runs"] == 3

    def test_build_prompt_length(self, adapter):
        """Prompt builder produces approximately correct token count."""
        prompt = adapter._build_prompt(512)
        # Rough check: prompt should be substantial
        assert len(prompt) > 1000

    def test_validate_ttft_rejects_invalid(self, adapter):
        """Validation rejects None, NaN, negative, zero."""
        assert not adapter._validate_ttft(None)
        assert not adapter._validate_ttft(-1.0)
        assert not adapter._validate_ttft(0.0)
        assert adapter._validate_ttft(0.5)


class TestBenchmarkSpec:
    """Test BenchmarkSpec import and defaults."""

    def test_import_and_defaults(self):
        from agent_llm_bench_v03.domain.models import BenchmarkSpec as BS

        spec = BS(name="test", version="1.0", category="performance")
        assert spec.timeout_sec == 300
