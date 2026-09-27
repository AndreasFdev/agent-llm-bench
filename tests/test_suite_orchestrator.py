"""Tests for suite orchestrator."""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from agent_llm_bench_v03.domain.models import (
    BenchmarkResult,
    RunStatus,
    SuiteRun,
)
from agent_llm_bench_v03.suite.orchestrator import BudgetTracker, SuiteOrchestrator
from agent_llm_bench_v03.suite.profiles import AdapterConfig, SuiteProfile


def make_suite_run() -> SuiteRun:
    return SuiteRun(
        suite_run_id="test-run-1",
        profile_name="quick",
        profile_version="1.0.0",
        model_name="test-model",
        node_id="node-2",
        status=RunStatus.RUNNING,
    )


def make_node_config():
    nc = MagicMock()
    nc.base_url = "http://192.168.188.8:9292"
    nc.api_key = "test-key"
    return nc


def make_profile(adapter_count=1, budget_sec=100):
    adapters = []
    for i in range(adapter_count):
        adapters.append(AdapterConfig(
            adapter_class=f"adapter_{i}",
            category="performance",
            profile="quick",
            params={"ctx_size": 65536},
        ))
    return SuiteProfile(
        name="test",
        version="1.0.0",
        description="Test profile",
        budget_sec=budget_sec,
        adapters=adapters,
    )


class TestBudgetTracker:
    """Budget tracking."""

    def test_initial_state(self):
        tracker = BudgetTracker(100)
        assert tracker.budget_sec == 100
        assert not tracker.exhausted
        assert tracker.remaining_sec > 0

    def test_exhausted_when_zero_budget(self):
        tracker = BudgetTracker(0)
        assert tracker.exhausted

    def test_remaining_decreases_over_time(self):
        import time
        tracker = BudgetTracker(100)
        initial = tracker.remaining_sec
        time.sleep(0.1)
        assert tracker.remaining_sec < initial


class TestOrchestratorDryRun:
    """Dry run mode: no processes, no DB writes."""

    def test_dry_run_skips_adapter_execution(self):
        profile = make_profile(adapter_count=2)
        db = MagicMock()
        orch = SuiteOrchestrator(
            profile=profile,
            suite_run=make_suite_run(),
            node_config=make_node_config(),
            database=db,
            dry_run=True,
        )

        with patch.object(orch, "_create_adapter") as mock_create:
            orch.run()
            # In dry run, no adapters should be created or executed
            mock_create.assert_not_called()
            db.create_benchmark_run.assert_not_called()
            db.complete_suite_run.assert_not_called()


class TestOrchestratorActiveFlag:
    """Active flag for controlled abort."""

    def test_is_active_without_flag(self):
        orch = SuiteOrchestrator(
            profile=make_profile(),
            suite_run=make_suite_run(),
            node_config=make_node_config(),
            dry_run=True,
        )
        assert orch._is_active()  # No flag configured = always active

    def test_aborts_when_flag_removed(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            flag_path = f.name

        try:
            profile = make_profile(adapter_count=2)
            orch = SuiteOrchestrator(
                profile=profile,
                suite_run=make_suite_run(),
                node_config=make_node_config(),
                dry_run=True,
                active_flag_path=flag_path,
            )

            # Flag exists, should be active
            assert orch._is_active()

            # Remove flag
            os.unlink(flag_path)

            # Should no longer be active
            assert not orch._is_active()
        finally:
            if os.path.exists(flag_path):
                os.unlink(flag_path)


class TestOrchestratorInfrastructureError:
    """Infrastructure errors fail fast and abort suite."""

    def test_connection_refused_returns_none(self):
        profile = make_profile(adapter_count=1)
        orch = SuiteOrchestrator(
            profile=profile,
            suite_run=make_suite_run(),
            node_config=make_node_config(),
            dry_run=False,
        )

        mock_adapter = MagicMock()
        mock_adapter.version = "1.0"
        mock_adapter.prepare.return_value = {"command": ["true"]}
        mock_adapter.validate.return_value = None
        mock_adapter.execute.side_effect = Exception("Connection refused")

        with patch.object(orch, "_create_adapter", return_value=mock_adapter):
            result = orch.run_adapter(profile.adapters[0])
            # Infrastructure error returns None to signal abort
            assert result is None


class TestOrchestratorPartialResults:
    """Failed adapters don't block the suite; partial results are saved."""

    def test_failed_adapter_continues_suite(self):
        profile = make_profile(adapter_count=2)
        orch = SuiteOrchestrator(
            profile=profile,
            suite_run=make_suite_run(),
            node_config=make_node_config(),
            dry_run=False,
        )

        # First adapter fails (non-infra error), second succeeds
        mock_adapter_fail = MagicMock()
        mock_adapter_fail.version = "1.0"
        mock_adapter_fail.prepare.return_value = {"command": ["true"]}
        mock_adapter_fail.validate.return_value = None
        mock_adapter_fail.execute.side_effect = Exception("Test failure")

        mock_adapter_ok = MagicMock()
        mock_adapter_ok.version = "1.0"
        mock_adapter_ok.prepare.return_value = {"command": ["true"]}
        mock_adapter_ok.validate.return_value = None
        mock_adapter_ok.execute.return_value = {"output": ""}
        mock_adapter_ok.parse.return_value = BenchmarkResult(
            schema_version="1.0",
            benchmark_name="adapter_1",
            benchmark_version="1.0",
            adapter_version="1.0",
            status=RunStatus.COMPLETED,
        )

        call_count = [0]
        def create_adapter_side_effect(config):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_adapter_fail
            return mock_adapter_ok

        with patch.object(orch, "_create_adapter", side_effect=create_adapter_side_effect):
            suite_run = orch.run()
            # Both adapters were attempted
            assert len(orch.results) == 2
            # Suite status should be partial (one failed, one succeeded)
            assert suite_run.status == RunStatus.PARTIAL


class TestOrchestratorBudgetExhaustion:
    """Budget exhaustion handling."""

    def test_budget_exhausted_stops_suite(self):
        profile = make_profile(adapter_count=3, budget_sec=1)
        orch = SuiteOrchestrator(
            profile=profile,
            suite_run=make_suite_run(),
            node_config=make_node_config(),
            dry_run=False,
        )

        # Make all adapters slow (sleep 2s each)
        import time
        def slow_adapter_factory(config):
            mock = MagicMock()
            mock.version = "1.0"
            mock.prepare.return_value = {"command": ["true"]}
            mock.validate.return_value = None
            def slow_execute(spec, runner, env):
                time.sleep(2)
                return {"output": ""}
            mock.execute.side_effect = slow_execute
            mock.parse.return_value = BenchmarkResult(
                schema_version="1.0",
                benchmark_name=config.adapter_class,
                benchmark_version="1.0",
                adapter_version="1.0",
                status=RunStatus.COMPLETED,
            )
            return mock

        with patch.object(orch, "_create_adapter", side_effect=slow_adapter_factory):
            suite_run = orch.run()
            # Should not run all 3 adapters due to budget
            assert len(orch.results) < 3
            # Status should reflect budget exhaustion or partial completion
            assert suite_run.status in (RunStatus.BUDGET_EXHAUSTED, RunStatus.PARTIAL, RunStatus.COMPLETED)
