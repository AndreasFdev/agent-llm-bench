"""BFCL-V4 Tool Calling adapter for V0.3.

Runs Berkeley Function Calling Leaderboard (BFCL) via the existing bfcl_run.py
wrapper. Supports simple_python and multiple categories.

Environment variables (provided by suite runner in env):
    BENCH_BASE_URL: Local endpoint URL (e.g., http://localhost:9292)
    BENCH_API_KEY:  API key for the endpoint

Profiles:
    QUICK: 40% of simple_python + 20% of multiple (deterministic subset by ID order)
    FULL: All items
"""

import json
import logging
import os
import subprocess
import time
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


class BfclAdapter(BenchmarkAdapter):
    """Adapter for BFCL-V4 tool calling benchmark."""

    name = "bfcl_tool_calling"
    version = "1.0.0"
    category = "tool_calling"
    timeout_sec = 300

    def __init__(
        self,
        profile: str = "quick",
        categories: list[str] | None = None,
        bfcl_root: Path | str | None = None,
    ):
        self.profile = profile.lower()
        # Quick: simple_python + multiple. Full: all categories.
        if categories is None:
            if self.profile == "quick":
                categories = ["simple_python", "multiple"]
            else:
                categories = ["simple_python", "multiple", "parallel", "memory"]
        self.categories = categories
        self.bfcl_root = Path(bfcl_root) if bfcl_root else Path(
            "/opt/nexus-cluster/bench/gorilla/berkeley-function-call-leaderboard"
        )
        self.bfcl_wrapper = Path("/opt/nexus-cluster/bench/bfcl_run.py")

    def _get_task_ids(self, category: str) -> list[str]:
        """Get task IDs for a BFCL category (deterministic ordering)."""
        data_file = self.bfcl_root / "bfcl_eval" / "data" / f"BFCL_v4_{category}.json"
        if not data_file.exists():
            return []
        try:
            with open(data_file) as f:
                lines = f.read().strip().splitlines()
            ids = []
            for line in lines:
                item = json.loads(line)
                ids.append(item.get("id", ""))
            # Quick profile: deterministic subset by ID order
            if self.profile == "quick":
                if category == "simple_python":
                    return ids[:40]  # ~40% of typical size
                elif category == "multiple":
                    return ids[:20]  # ~20% of typical size
            return ids
        except Exception as e:
            logger.warning(f"Could not read BFCL data file {data_file}: {e}")
            return []

    def prepare(self, suite_run: SuiteRun, config: dict[str, Any]) -> BenchmarkSpec:
        """Prepare benchmark spec with task selection."""
        all_task_ids = []
        for cat in self.categories:
            all_task_ids.extend(self._get_task_ids(cat))

        return BenchmarkSpec(
            name=self.name,
            version=self.version,
            category=self.category,
            task_ids=all_task_ids,
            timeout_sec=self.timeout_sec,
            command_vars={
                "profile": self.profile,
                "categories": self.categories,
                "bfcl_root": str(self.bfcl_root),
            },
        )

    def validate(self, spec: BenchmarkSpec) -> None:
        """Validate that BFCL environment is ready."""
        if not self.bfcl_root.exists():
            raise ValueError(f"BFCL root not found: {self.bfcl_root}")
        if not self.bfcl_wrapper.exists():
            raise ValueError(f"BFCL wrapper script not found: {self.bfcl_wrapper}")
        # Check that at least one category has tasks
        total_tasks = sum(len(self._get_task_ids(cat)) for cat in self.categories)
        if total_tasks == 0:
            raise ValueError("No BFCL tasks found for configured categories")

    def execute(
        self,
        spec: BenchmarkSpec,
        runner: ProcessRunner,
        env: dict[str, str],
    ) -> dict[str, Any]:
        """Run BFCL generate + evaluate."""
        base_url = env.get("BENCH_BASE_URL", "http://localhost:9292")
        api_key = env.get("BENCH_API_KEY", "")

        # Build test-category string for BFCL
        category_str = ",".join(self.categories)

        # Step 1: Generate
        model_key = f"bench-{int(time.time())}"
        generate_cmd = [
            "python3", str(self.bfcl_wrapper), "generate",
            "--model", model_key,
            "--test-category", category_str,
            "--temperature", "0.001",
            "--skip-server-setup",
            "--num-threads", "4",
        ]

        gen_env = os.environ.copy()
        gen_env["OPENAI_BASE_URL"] = base_url.rstrip("/") + "/v1"
        gen_env["OPENAI_API_KEY"] = api_key or "dummy-key-for-local"

        logger.info("BFCL: Running generate...")
        try:
            gen_result = runner.run(generate_cmd, timeout=self.timeout_sec // 2, env=gen_env)
            if gen_result.exit_code != 0:
                logger.error(f"BFCL generate failed (exit {gen_result.exit_code})")
                return {"status": "failed", "error": f"generate failed: {gen_result.stderr[:500]}"}
        except Exception as e:
            logger.error(f"BFCL generate exception: {e}")
            return {"status": "failed", "error": str(e)}

        # Step 2: Evaluate
        evaluate_cmd = [
            "python3", str(self.bfcl_wrapper), "evaluate",
            "--model", model_key,
            "--test-category", "all_scoring",
        ]

        logger.info("BFCL: Running evaluate...")
        try:
            eval_result = runner.run(evaluate_cmd, timeout=self.timeout_sec // 2, env=gen_env)
        except Exception as e:
            logger.error(f"BFCL evaluate exception: {e}")
            return {"status": "failed", "error": str(e)}

        # Parse evaluation output (BFCL prints results to stdout)
        output = eval_result.stdout or ""
        return {"raw_output": output, "model_key": model_key}

    def parse(self, raw: dict[str, Any], spec: BenchmarkSpec) -> BenchmarkResult:
        """Parse BFCL evaluation output into canonical result."""
        if raw.get("status") == "failed":
            return BenchmarkResult(
                schema_version="1.0",
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error={"error_class": "execution_error", "message": raw.get("error", "")},
            )

        output = raw.get("raw_output", "")

        # BFCL outputs lines like:
        # "simple_python accuracy: 0.85" or similar format
        # Try to extract scores
        total_score = 0.0
        total_count = 0
        category_scores = {}

        for line in output.splitlines():
            line = line.strip()
            # Look for patterns like "category accuracy: X.XX" or "score: X/X"
            if "accuracy" in line.lower() and ":" in line:
                parts = line.split(":")
                try:
                    score_val = float(parts[-1].strip())
                    cat_name = parts[0].strip().lower()
                    if 0 <= score_val <= 1.0:
                        category_scores[cat_name] = score_val
                        total_score += score_val
                        total_count += 1
                except (ValueError, IndexError):
                    pass

        # If no scores found in output, mark as failed to parse
        if total_count == 0:
            return BenchmarkResult(
                schema_version="1.0",
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error={"error_class": "parse_error", "message": f"Could not parse BFCL output: {output[:500]}"},
            )

        avg_score = (total_score / total_count * 100.0) if total_count > 0 else 0.0

        # Build task results per category
        tasks = []
        for cat, score in category_scores.items():
            tasks.append(TaskResult(
                task_id=f"bfcl_{cat}",
                status=RunStatus.COMPLETED,
                raw_score=score * 100.0,
                normalized_score=score * 100.0,
                metadata={"category": cat, "score_pct": score * 100.0},
            ))

        return BenchmarkResult(
            schema_version="1.0",
            benchmark_name=self.name,
            benchmark_version=self.version,
            adapter_version=self.version,
            status=RunStatus.COMPLETED,
            raw_score=avg_score,
            normalized_score=avg_score,
            task_results=tasks,
            metadata={
                "profile": spec.command_vars.get("profile", self.profile),
                "categories": spec.command_vars.get("categories", self.categories),
                "category_scores": category_scores,
            },
        )
