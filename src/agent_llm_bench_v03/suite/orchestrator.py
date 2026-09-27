"""Suite orchestrator: runs a profile's adapters with budget management.

Key behaviors (per concept doc):
- Sequential adapter execution
- Per-adapter timeout (default 300s)
- Total suite budget; budget exhaustion → remaining adapters skipped, status=budget_exhausted
- Partial results are saved even on timeout/failure
- Suite continues to next adapter after a failure (non-blocking)
- All results recorded to SQLite database
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from agent_llm_bench_v03.domain.models import (
    BenchmarkResult,
    RunStatus,
    SuiteRun,
)
from agent_llm_bench_v03.runner.process_runner import ProcessRunner
from agent_llm_bench_v03.suite.profiles import SuiteProfile, AdapterConfig

logger = logging.getLogger(__name__)


class BudgetTracker:
    """Tracks elapsed time against a budget."""

    def __init__(self, budget_sec: int):
        self.budget_sec = budget_sec
        self._start = time.monotonic()
        self._paused_at: float | None = None

    @property
    def elapsed_sec(self) -> float:
        end = self._paused_at if self._paused_at else time.monotonic()
        return end - self._start

    @property
    def remaining_sec(self) -> float:
        return max(0.0, self.budget_sec - self.elapsed_sec)

    @property
    def exhausted(self) -> bool:
        return self.remaining_sec <= 0

    def pause(self):
        if not self._paused_at:
            self._paused_at = time.monotonic()

    def resume(self):
        if self._paused_at:
            # Adjust start to account for pause duration
            paused_for = time.monotonic() - self._paused_at
            self._start += paused_for
            self._paused_at = None


class SuiteOrchestrator:
    """Orchestrates a benchmark suite run."""

    def __init__(
        self,
        profile: SuiteProfile,
        suite_run: SuiteRun,
        node_config: Any,
        database=None,
        dry_run: bool = False,
        active_flag_path: str | None = None,
    ):
        self.profile = profile
        self.suite_run = suite_run
        self.node_config = node_config
        self.database = database
        self.dry_run = dry_run
        self.active_flag_path = active_flag_path
        self.budget = BudgetTracker(profile.budget_sec)
        self.results: list[BenchmarkResult] = []
        self._adapter_instances: dict[str, Any] = {}

    def _is_active(self) -> bool:
        """Check if the active flag file exists (suite should continue)."""
        if not self.active_flag_path:
            return True  # No flag configured, always active
        import os
        return os.path.exists(self.active_flag_path)

    def _create_adapter(self, config: AdapterConfig):
        """Instantiate an adapter from its configuration."""
        # Import adapter classes dynamically
        if config.adapter_class == "llama_benchy":
            from agent_llm_bench_v03.adapters.performance.llama_benchy_adapter import LlamaBenchyAdapter
            return LlamaBenchyAdapter(profile=config.profile)
        elif config.adapter_class == "ttft":
            from agent_llm_bench_v03.adapters.performance.ttft_adapter import TtftAdapter
            return TtftAdapter(profile=config.profile)
        elif config.adapter_class == "local_agent_benchmark":
            from agent_llm_bench_v03.adapters.local_agent.local_agent_adapter import LocalAgentAdapter
            return LocalAgentAdapter()
        elif config.adapter_class == "bfcl_tool_calling":
            from agent_llm_bench_v03.adapters.tool_calling.bfcl_adapter import BfclAdapter
            return BfclAdapter(profile=config.profile)
        elif config.adapter_class == "instruction_following":
            from agent_llm_bench_v03.adapters.instruction.instruction_adapter import InstructionAdapter
            return InstructionAdapter(profile=config.profile)
        else:
            raise ValueError(f"Unknown adapter class: {config.adapter_class}")

    def _build_env(self) -> dict[str, str]:
        """Build environment variables for adapters."""
        env = {}
        if self.node_config.base_url:
            env["BENCH_BASE_URL"] = self.node_config.base_url
        if self.node_config.api_key:
            env["BENCH_API_KEY"] = self.node_config.api_key
        return env

    def run_adapter(self, config: AdapterConfig) -> BenchmarkResult | None:
        """Run a single adapter with budget and timeout management."""
        # Check budget before starting
        if self.budget.exhausted:
            logger.warning(f"Budget exhausted, skipping {config.adapter_class}")
            return None

        logger.info(f"Running adapter: {config.adapter_class} (budget remaining: {self.budget.remaining_sec:.0f}s)")

        try:
            adapter = self._create_adapter(config)
        except Exception as e:
            logger.error(f"Failed to create adapter {config.adapter_class}: {e}")
            return BenchmarkResult(
                schema_version="1.0",
                benchmark_name=config.adapter_class,
                benchmark_version="unknown",
                adapter_version="unknown",
                status=RunStatus.FAILED,
                error={"error_class": "setup_error", "message": str(e)},
            )

        # Prepare
        try:
            spec = adapter.prepare(self.suite_run, config.params)
        except Exception as e:
            logger.error(f"Adapter {config.adapter_class} prepare failed: {e}")
            return BenchmarkResult(
                schema_version="1.0",
                benchmark_name=config.adapter_class,
                benchmark_version=adapter.version,
                adapter_version=adapter.version,
                status=RunStatus.FAILED,
                error={"error_class": "prepare_error", "message": str(e)},
            )

        # Validate
        try:
            adapter.validate(spec)
        except Exception as e:
            logger.error(f"Adapter {config.adapter_class} validate failed: {e}")
            return BenchmarkResult(
                schema_version="1.0",
                benchmark_name=config.adapter_class,
                benchmark_version=adapter.version,
                adapter_version=adapter.version,
                status=RunStatus.FAILED,
                error={"error_class": "validation_error", "message": str(e)},
            )

        # Execute with ProcessRunner (handles timeout)
        runner = ProcessRunner(
            timeout_sec=min(config.timeout_sec, int(self.budget.remaining_sec)),
        )
        env = self._build_env()

        try:
            raw = adapter.execute(spec, runner, env)
        except Exception as e:
            error_msg = str(e).lower()
            # Infrastructure errors: fail fast, don't continue suite
            is_infra_error = any(
                kw in error_msg
                for kw in ["connection refused", "connection timed out", "could not connect",
                           "max retries exceeded", "failed to establish connection"]
            )
            if is_infra_error:
                logger.error(f"INFRASTRUCTURE ERROR in {config.adapter_class}: {e}")
                return None  # Signal caller to abort suite
            logger.error(f"Adapter {config.adapter_class} execute failed: {e}")
            return BenchmarkResult(
                schema_version="1.0",
                benchmark_name=config.adapter_class,
                benchmark_version=adapter.version,
                adapter_version=adapter.version,
                status=RunStatus.FAILED,
                error={"error_class": "execution_error", "message": str(e)},
            )

        # Parse results
        try:
            result = adapter.parse(raw, spec)
        except Exception as e:
            logger.error(f"Adapter {config.adapter_class} parse failed: {e}")
            return BenchmarkResult(
                schema_version="1.0",
                benchmark_name=config.adapter_class,
                benchmark_version=adapter.version,
                adapter_version=adapter.version,
                status=RunStatus.FAILED,
                error={"error_class": "parse_error", "message": str(e)},
            )

        # Record duration
        result.metadata["elapsed_sec"] = self.budget.elapsed_sec

        return result

    def _is_already_completed(self, benchmark_name: str) -> bool:
        """Check if a benchmark has already completed successfully for this suite run."""
        if not self.database:
            return False
        try:
            runs = self.database.list_benchmark_runs(suite_run_id=self.suite_run.suite_run_id)
            for run in runs:
                if run["benchmark_name"] == benchmark_name and run["status"] == "completed":
                    return True
        except Exception as e:
            logger.warning(f"Failed to check completed benchmarks: {e}")
        return False

    def run(self) -> SuiteRun:
        """Execute the full suite profile."""
        logger.info(f"Starting suite: {self.profile.name} (budget: {self.profile.budget_sec}s)")
        if self.dry_run:
            logger.info("DRY RUN: no processes will be started, no DB writes")

        for config in self.profile.adapters:
            # Resume support: skip already-completed benchmarks
            if not self.dry_run and self._is_already_completed(config.adapter_class):
                logger.info(f"Skipping {config.adapter_class}: already completed in this suite run")
                continue
            # Check active flag for controlled abort
            if not self._is_active():
                logger.warning("Active flag removed, aborting suite")
                break

            if self.budget.exhausted:
                logger.warning("Suite budget exhausted, stopping")
                break

            if self.dry_run:
                logger.info(f"[DRY RUN] Would run adapter: {config.adapter_class} (timeout={config.timeout_sec}s)")
                continue

            result = self.run_adapter(config)
            if result is None:
                # Infrastructure error or budget exhausted - abort suite
                logger.error("Aborting suite due to infrastructure error")
                break
            self.results.append(result)
            if self.database and not self.dry_run:
                try:
                    self.database.create_benchmark_run(
                        suite_run_id=self.suite_run.suite_run_id,
                        benchmark_name=result.benchmark_name,
                        benchmark_version=result.benchmark_version,
                        adapter_version=result.adapter_version,
                        status=result.status.value,
                        duration_sec=0.0,
                    )
                except Exception as e:
                    logger.error(f"Failed to record result to database: {e}")

        # Determine final suite status
        if self.budget.exhausted and len(self.results) < len(self.profile.adapters):
            status = RunStatus.BUDGET_EXHAUSTED
        elif not self.results:
            status = RunStatus.FAILED
        else:
            completed = sum(1 for r in self.results if r.status == RunStatus.COMPLETED)
            if completed == len(self.profile.adapters):
                status = RunStatus.COMPLETED
            elif completed > 0:
                status = RunStatus.PARTIAL
            else:
                status = RunStatus.FAILED

        self.suite_run.status = status
        self.suite_run.finished_at = datetime.now(timezone.utc)

        # Final database record
        if self.database and not self.dry_run:
            try:
                self.database.complete_suite_run(
                    suite_run_id=self.suite_run.suite_run_id,
                    status=status.value,
                    error_message=None,
                )
            except Exception as e:
                logger.error(f"Failed to record suite completion: {e}")

        logger.info(f"Suite completed with status: {status.value}")
        return self.suite_run
