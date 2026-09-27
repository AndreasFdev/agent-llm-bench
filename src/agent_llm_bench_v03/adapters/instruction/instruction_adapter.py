"""Instruction following benchmark adapter (IFEval + IFBench via lm-eval-harness).

Runs IFEval and IFBench through the lm-eval-harness CLI. Supports quick (subset)
and full profiles.

Environment variables:
    BENCH_BASE_URL: Local endpoint URL (e.g., http://localhost:9292)
    BENCH_API_KEY:  API key for the endpoint
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


class InstructionAdapter(BenchmarkAdapter):
    """Adapter for instruction following benchmarks (IFEval, IFBench)."""

    name = "instruction_following"
    version = "1.0.0"
    category = "instruction_following"
    timeout_sec = 300

    def __init__(self, profile: str = "quick", tasks: list[str] | None = None):
        self.profile = profile.lower()
        # Quick: IFEval only (subset). Full: IFEval + IFBench.
        if tasks is None:
            if self.profile == "quick":
                tasks = ["ifeval"]
            else:
                tasks = ["ifeval", "ifbench"]
        self.tasks = tasks
        # Limit for quick profile (deterministic subset via lm-eval --limit)
        self.limit = 40 if self.profile == "quick" else None

    def prepare(self, suite_run: SuiteRun, config: dict[str, Any]) -> BenchmarkSpec:
        """Prepare benchmark spec."""
        return BenchmarkSpec(
            name=self.name,
            version=self.version,
            category=self.category,
            task_ids=[],  # lm-eval determines tasks internally
            timeout_sec=self.timeout_sec,
            command_vars={
                "profile": self.profile,
                "tasks": self.tasks,
                "limit": self.limit,
            },
        )

    def validate(self, spec: BenchmarkSpec) -> None:
        """Validate that lm-eval is available."""
        try:
            subprocess.run(
                ["which", "lm_eval"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception as e:
            raise ValueError(f"lm_eval not found or not executable: {e}")

    def execute(
        self,
        spec: BenchmarkSpec,
        runner: ProcessRunner,
        env: dict[str, str],
    ) -> dict[str, Any]:
        """Run lm-eval for instruction following tasks."""
        base_url = env.get("BENCH_BASE_URL", "http://localhost:9292")
        api_key = env.get("BENCH_API_KEY", "")

        results_dir = Path(f"/tmp/lm_eval_results_{int(time.time())}")
        results_dir.mkdir(parents=True, exist_ok=True)

        all_task_output = {}

        for task in self.tasks:
            # Build lm-eval command
            cmd = [
                "lm_eval",
                "--model", "local_llm",
                "--tasks", task,
                "--batch_size", "auto",
                f"--model_args", f"device=cpu,base_url={base_url.rstrip('/')}/v1,max_tokens=512",
                "--log_samples",
                f"--output_path", str(results_dir),
                "--apply_chat_template",
            ]

            if self.limit:
                cmd.extend(["--limit", str(self.limit)])

            logger.info(f"Instruction: Running lm_eval for {task}...")
            try:
                result = runner.run(cmd, timeout=self.timeout_sec // len(self.tasks))
                output = result.stdout or ""

                # Parse JSON results from lm-eval output
                task_result = self._parse_lm_eval_output(output)
                all_task_output[task] = {
                    "exit_code": result.exit_code,
                    "output": output,
                    "parsed": task_result,
                }
            except Exception as e:
                logger.error(f"lm_eval failed for {task}: {e}")
                all_task_output[task] = {"exit_code": -1, "error": str(e)}

        return {"task_results": all_task_output}

    def _parse_lm_eval_output(self, output: str) -> dict | None:
        """Parse lm-eval JSON output from stdout."""
        # lm-eval prints a JSON block at the end
        lines = output.strip().splitlines()
        # Find the last line that looks like JSON (starts with { or [)
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None

    def parse(self, raw: dict[str, Any], spec: BenchmarkSpec) -> BenchmarkResult:
        """Parse lm-eval results into canonical result."""
        task_results_data = raw.get("task_results", {})

        if not task_results_data:
            return BenchmarkResult(
                schema_version="1.0",
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error={"error_class": "execution_error", "message": "No task results"},
            )

        tasks = []
        scores = []

        for task_name, data in task_results_data.items():
            if data.get("exit_code", -1) != 0:
                tasks.append(TaskResult(
                    task_id=f"instr_{task_name}",
                    status=RunStatus.FAILED,
                    error={"error_class": "execution_error", "message": data.get("error", "")},
                ))
                continue

            parsed = data.get("parsed")
            if not parsed:
                tasks.append(TaskResult(
                    task_id=f"instr_{task_name}",
                    status=RunStatus.FAILED,
                    error={"error_class": "parse_error", "message": "Could not parse lm-eval output"},
                ))
                continue

            # Extract score from lm-eval results
            # Format: {"results": {"ifeval": {"prompt_str_match_exact,exact_match": 0.85}}}
            task_scores = parsed.get("results", {}).get(task_name, {})
            score = None
            for metric_name, value in task_scores.items():
                if isinstance(value, (int, float)):
                    # Prefer exact_match or accuracy metrics
                    if "exact" in metric_name.lower() or "accuracy" in metric_name.lower():
                        score = value
                        break
                    elif score is None:
                        score = value

            if score is not None:
                # Convert to percentage if needed (lm-eval uses 0-1 scale)
                score_pct = score * 100.0 if score <= 1.0 else score
                tasks.append(TaskResult(
                    task_id=f"instr_{task_name}",
                    status=RunStatus.COMPLETED,
                    raw_score=score_pct,
                    normalized_score=score_pct,
                    metadata={"metric": metric_name},
                ))
                scores.append(score_pct)
            else:
                tasks.append(TaskResult(
                    task_id=f"instr_{task_name}",
                    status=RunStatus.FAILED,
                    error={"error_class": "parse_error", "message": f"No numeric score found in {task_scores}"},
                ))

        # Calculate overall score (average of completed tasks)
        if scores:
            avg_score = sum(scores) / len(scores)
            status = RunStatus.COMPLETED
        else:
            avg_score = 0.0
            status = RunStatus.FAILED

        return BenchmarkResult(
            schema_version="1.0",
            benchmark_name=self.name,
            benchmark_version=self.version,
            adapter_version=self.version,
            status=status,
            raw_score=avg_score,
            normalized_score=avg_score,
            task_results=tasks,
            metadata={
                "profile": spec.command_vars.get("profile", self.profile),
                "tasks": spec.command_vars.get("tasks", self.tasks),
            },
        )
