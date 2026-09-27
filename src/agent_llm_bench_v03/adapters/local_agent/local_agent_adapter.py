"""Local Agent Benchmark adapter.

Runs the local-agent-benchmark T1-T17 test suite against a model endpoint and
parses results into the canonical V0.3 BenchmarkResult format.

Usage:
    adapter = LocalAgentAdapter()
    spec = adapter.prepare(suite_run, config)
    adapter.validate(spec)
    raw = adapter.execute(spec, runner, env)
    result = adapter.parse(raw, spec)
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_llm_bench_v03.domain.adapter import BenchmarkAdapter
from agent_llm_bench_v03.domain.models import (
    BenchmarkResult,
    BenchmarkSpec,
    RunStatus,
    SuiteRun,
    TaskResult,
)
from agent_llm_bench_v03.runner.process_runner import ProcessRunner

logger = logging.getLogger(__name__)

# Default path to local-agent-benchmark repo
DEFAULT_BENCHMARK_PATH = Path("/opt/nexus-cluster/bench/local-agent-benchmark")


class LocalAgentAdapter(BenchmarkAdapter):
    """Adapter for the local-agent-benchmark T1-T17 suite."""

    name = "local_agent_benchmark"
    version = "1.0.0"
    category = "agentic"
    timeout_sec = 480  # 8 minutes target budget for Quick profile

    def __init__(self, benchmark_path: Path | None = None, include_hop: bool = False):
        self.benchmark_path = benchmark_path or DEFAULT_BENCHMARK_PATH
        self.include_hop = include_hop  # T-HOP excluded in Quick profile

    def prepare(self, suite_run: SuiteRun, config: dict[str, Any]) -> BenchmarkSpec:
        """Prepare benchmark spec with task selection."""
        return BenchmarkSpec(
            name=self.name,
            version=self.version,
            category=self.category,
            task_ids=[f"T{i}" for i in range(1, 18)],  # T1-T17
            timeout_sec=self.timeout_sec,
            command_vars={
                "benchmark_path": str(self.benchmark_path),
                "include_hop": self.include_hop,
            },
        )

    def validate(self, spec: BenchmarkSpec) -> None:
        """Validate that benchmark repo exists and is executable."""
        bench_path = Path(spec.command_vars.get("benchmark_path", str(self.benchmark_path)))
        if not bench_path.exists():
            raise ValueError(f"Benchmark path does not exist: {bench_path}")

        harness = bench_path / "tests" / "harness.py"
        if not harness.exists():
            raise ValueError(f"Harness script not found: {harness}")

        # Check for Python dependencies
        try:
            result = subprocess.run(
                ["python3", "-c", "import openai; import rich"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning("Some Python dependencies may be missing: %s", result.stderr)
        except Exception as e:
            logger.warning("Could not check dependencies: %s", e)

    def execute(
        self,
        spec: BenchmarkSpec,
        runner: ProcessRunner,
        env: dict[str, str],
    ) -> dict[str, Any]:
        """Execute the local-agent-benchmark harness."""
        bench_path = Path(spec.command_vars.get("benchmark_path", str(self.benchmark_path)))
        include_hop = spec.command_vars.get("include_hop", False)

        # Build command
        cmd = [
            "python3", "-m", "tests.harness",
            "--model", "bench-model",  # Model name from endpoint
            "--machine", "nexus-bench-v03",
            "--skip-hop",
        ]
        if include_hop:
            cmd.remove("--skip-hop")

        # Set up environment for the subprocess
        process_env = os.environ.copy()
        process_env["BENCH_BASE_URL"] = env.get("BENCH_BASE_URL", "http://localhost:9292")
        process_env["BENCH_API_KEY"] = env.get("BENCH_API_KEY", "")
        process_env["RESULTS_DIR"] = str(Path("/tmp/agent-bench-results"))

        # Create results directory
        Path("/tmp/agent-bench-results").mkdir(parents=True, exist_ok=True)

        logger.info("Running local-agent-benchmark: %s", " ".join(cmd))

        try:
            result = runner.run(
                cmd,
                cwd=str(bench_path),
                env=process_env,
                timeout=self.timeout_sec,
            )
        except Exception as e:
            logger.error("Benchmark execution failed: %s", e)
            return {"status": "failed", "error": str(e)}

        # Find the results file
        results_file = self._find_results_file()

        if not results_file:
            return {
                "status": "failed",
                "error": "No results file found after execution",
                "exit_code": result.exit_code,
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "stderr": result.stderr[-2000:] if result.stderr else "",
            }

        try:
            with open(results_file, "r") as f:
                raw_results = json.load(f)
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Failed to parse results file: {e}",
                "results_file": str(results_file),
            }

        return {
            "status": "completed",
            "raw_results": raw_results,
            "results_file": str(results_file),
            "exit_code": result.exit_code,
        }

    def _find_results_file(self) -> Path | None:
        """Find the most recent results.json file."""
        results_dir = Path("/tmp/agent-bench-results")
        if not results_dir.exists():
            return None

        # Search for results.json files
        candidates = list(results_dir.rglob("results.json"))
        if not candidates:
            return None

        # Return most recent by modification time
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def parse(self, raw: dict[str, Any], spec: BenchmarkSpec) -> BenchmarkResult:
        """Parse benchmark output into canonical result format."""
        if raw.get("status") == "failed":
            return BenchmarkResult(
                schema_version="1.0",
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error={"error_class": "execution_error", "message": raw.get("error", "")},
            )

        raw_results = raw.get("raw_results", {})
        tests = raw_results.get("tests", [])

        # Parse individual task results
        task_results = []
        passed = 0
        failed = 0
        human_review = 0

        for test in tests:
            tid = test.get("id", "unknown")
            status = test.get("status", "error")
            passed_flag = test.get("pass")
            reason = test.get("reason", "")
            latency_ms = test.get("latency_ms", 0)

            if passed_flag is True:
                task_status = RunStatus.COMPLETED
                passed += 1
            elif passed_flag is False:
                task_status = RunStatus.FAILED
                failed += 1
            else:
                task_status = RunStatus.PARTIAL
                human_review += 1

            task_results.append(TaskResult(
                task_id=tid,
                status=task_status,
                raw_score=1.0 if passed_flag is True else 0.0,
                normalized_score=100.0 if passed_flag is True else 0.0,
                duration_sec=(latency_ms / 1000.0) if latency_ms else None,
                metadata={
                    "reason": reason,
                    "tool_calls": len(test.get("tool_calls", [])),
                    "response_length": len(test.get("response", "")),
                },
            ))

        # Calculate aggregate score
        total = len(task_results)
        if total > 0:
            score_pct = (passed / total) * 100.0
        else:
            score_pct = 0.0

        # Determine overall status
        if failed == 0 and human_review == 0 and passed == total:
            status = RunStatus.COMPLETED
        elif passed > 0 or human_review > 0:
            status = RunStatus.PARTIAL
        else:
            status = RunStatus.FAILED

        return BenchmarkResult(
            schema_version="1.0",
            benchmark_name=self.name,
            benchmark_version=raw_results.get("suite_version", "unknown"),
            adapter_version=self.version,
            status=status,
            raw_score=score_pct,
            normalized_score=score_pct,
            duration_sec=sum(t.duration_sec or 0 for t in task_results),
            task_results=task_results,
            metadata={
                "model": raw_results.get("model", ""),
                "machine": raw_results.get("machine", ""),
                "run_date": raw_results.get("run_date", ""),
                "endpoint": raw_results.get("endpoint", ""),
                "total_tests": total,
                "passed": passed,
                "failed": failed,
                "human_review": human_review,
            },
        )
