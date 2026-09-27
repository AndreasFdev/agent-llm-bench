"""Benchmark adapter interface for V0.3.

All adapters implement this contract to integrate with the suite runner.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from agent_llm_bench_v03.domain.models import (
    BenchmarkResult,
    BenchmarkSpec,
    SuiteRun,
)
from agent_llm_bench_v03.runner.process_runner import ProcessRunner


class BenchmarkAdapter(ABC):
    """Base class for all benchmark adapters."""

    name: str = ""
    version: str = "1.0"
    category: str = ""  # performance, agentic, tool_calling, coding, instruction
    timeout_sec: int = 300

    @abstractmethod
    def prepare(self, suite_run: SuiteRun, config: dict[str, Any]) -> BenchmarkSpec:
        """Prepare the benchmark specification for this run.

        Returns a BenchmarkSpec with task selection, command template, etc.
        """
        raise NotImplementedError

    @abstractmethod
    def validate(self, spec: BenchmarkSpec) -> None:
        """Validate that prerequisites are met before running.

        Raises ValueError if validation fails.
        """
        raise NotImplementedError

    @abstractmethod
    def execute(
        self,
        spec: BenchmarkSpec,
        runner: ProcessRunner,
        env: dict[str, str],
    ) -> dict[str, Any]:
        """Execute the benchmark and return raw results.

        Args:
            spec: The benchmark specification
            runner: The process runner for executing commands
            env: Environment variables (includes BENCH_BASE_URL, BENCH_API_KEY)

        Returns:
            Raw result dictionary to be parsed by parse()
        """
        raise NotImplementedError

    @abstractmethod
    def parse(self, raw: dict[str, Any], spec: BenchmarkSpec) -> BenchmarkResult:
        """Parse raw results into the canonical BenchmarkResult format.

        Args:
            raw: Raw output from execute()
            spec: The benchmark specification

        Returns:
            Canonical BenchmarkResult with task-level details
        """
        raise NotImplementedError

    def run(
        self,
        suite_run: SuiteRun,
        config: dict[str, Any],
        runner: ProcessRunner,
        env: dict[str, str],
    ) -> BenchmarkResult:
        """Full adapter lifecycle: prepare -> validate -> execute -> parse.

        This is the standard entry point called by the suite runner.
        """
        spec = self.prepare(suite_run, config)
        self.validate(spec)
        raw = self.execute(spec, runner, env)
        return self.parse(raw, spec)


class FakeAdapter(BenchmarkAdapter):
    """Test adapter that produces deterministic results without side effects."""

    name = "fake"
    version = "1.0"
    category = "test"

    def __init__(self, results: list[dict] | None = None, fail_at: int | None = None):
        self._results = results or [{"task_id": "t1", "passed": True, "score": 1.0}]
        self._fail_at = fail_at

    def prepare(self, suite_run: SuiteRun, config: dict[str, Any]) -> BenchmarkSpec:
        return BenchmarkSpec(
            name=self.name,
            version=self.version,
            category=self.category,
            task_ids=[r["task_id"] for r in self._results],
            timeout_sec=10,
        )

    def validate(self, spec: BenchmarkSpec) -> None:
        pass

    def execute(self, spec: BenchmarkSpec, runner: ProcessRunner, env: dict[str, str]) -> dict[str, Any]:
        return {"raw_tasks": self._results}

    def parse(self, raw: dict[str, Any], spec: BenchmarkSpec) -> BenchmarkResult:
        from agent_llm_bench_v03.domain.models import TaskResult, RunStatus

        tasks = []
        for i, r in enumerate(raw["raw_tasks"]):
            if self._fail_at is not None and i == self._fail_at:
                tasks.append(TaskResult(
                    task_id=r["task_id"],
                    status=RunStatus.FAILED,
                    raw_score=0.0,
                ))
            else:
                tasks.append(TaskResult(
                    task_id=r["task_id"],
                    status=RunStatus.COMPLETED,
                    raw_score=r.get("score", 1.0 if r.get("passed") else 0.0),
                    normalized_score=r.get("score", 1.0 if r.get("passed") else 0.0),
                ))

        scores = [t.raw_score for t in tasks if t.raw_score is not None]
        avg = sum(scores) / len(scores) if scores else 0.0

        return BenchmarkResult(
            schema_version="1.0",
            benchmark_name=self.name,
            benchmark_version=self.version,
            adapter_version=self.version,
            status=RunStatus.COMPLETED,
            raw_score=avg,
            normalized_score=avg,
            task_results=tasks,
        )
