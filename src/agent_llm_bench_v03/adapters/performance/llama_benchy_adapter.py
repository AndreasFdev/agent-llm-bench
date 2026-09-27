"""Llama-benchy throughput adapter for V0.3.

Runs llama-benchy via ProcessRunner and parses the JSON output into
the canonical BenchmarkResult format. No direct DB writes.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Optional

from agent_llm_bench_v03.domain.adapter import BenchmarkAdapter
from agent_llm_bench_v03.domain.models import (
    ArtifactRef,
    BenchmarkResult,
    BenchmarkSpec,
    FailureInfo,
    SuiteRun,
    TaskResult,
)
from agent_llm_bench_v03.domain.status import RunStatus
from agent_llm_bench_v03.runner.process_runner import ProcessRunner


class LlamaBenchyAdapter(BenchmarkAdapter):
    """Runs llama-benchy and parses throughput results.

    Quick profile: single context depth, 2 runs, 1 warmup (~2 min).
    Full profile: multiple depths, 3 runs, 2 warmups.
    """

    name = "llama_benchy"
    version = "1.0"
    category = "performance"
    timeout_sec = 240  # Quick must fit in 4 min budget

    def __init__(self, llama_benchy_dir: str = "/opt/nexus-cluster/bench/llama-benchy"):
        self.llama_benchy_dir = Path(llama_benchy_dir)
        self.python_bin = self.llama_benchy_dir / ".venv" / "bin" / "python"

    def prepare(self, suite_run: SuiteRun, config: dict[str, Any]) -> BenchmarkSpec:
        profile = config.get("profile", "quick")
        if profile == "quick":
            runs = 2
            warmup = 1
            depths = [config.get("depth", 61440)]
        else:
            runs = 3
            warmup = 2
            depths = config.get("depths", [32768, 61440])

        return BenchmarkSpec(
            name=self.name,
            version=self.version,
            category=self.category,
            task_ids=[f"depth-{d}" for d in depths],
            timeout_sec=self.timeout_sec,
            command_template=(
                "cd {benchy_dir} && {python} -m llama_benchy "
                "--base-url {base_url} --api-key {api_key} --model {model} "
                "--tokenizer {tokenizer} --depth {depths} "
                "--runs {runs} --warmup-runs {warmup} "
                "--latency-mode generation --format json --save-result {output}"
            ),
            command_vars={
                "benchy_dir": str(self.llama_benchy_dir),
                "python": str(self.python_bin),
                "runs": runs,
                "warmup": warmup,
                "depths": depths,
            },
        )

    def validate(self, spec: BenchmarkSpec) -> None:
        if not self.llama_benchy_dir.exists():
            raise ValueError(f"llama-benchy directory not found: {self.llama_benchy_dir}")
        if not self.python_bin.exists():
            raise ValueError(f"llama-benchy python not found: {self.python_bin}")

    def execute(
        self,
        spec: BenchmarkSpec,
        runner: ProcessRunner,
        env: dict[str, str],
    ) -> dict[str, Any]:
        base_url = env.get("BENCH_BASE_URL", "")
        api_key = env.get("BENCH_API_KEY", "")
        model = env.get("BENCH_MODEL", "default")
        tokenizer = env.get("BENCH_TOKENIZER", "Qwen/Qwen2.5-7B-Instruct")

        # Output file in temp dir
        output_file = f"/tmp/llama-benchy-{os.getpid()}.json"

        depths_str = " ".join(str(d) for d in spec.command_vars["depths"])
        command = spec.command_template.format(
            benchy_dir=spec.command_vars["benchy_dir"],
            python=spec.command_vars["python"],
            base_url=base_url,
            api_key=api_key,
            model=model,
            tokenizer=tokenizer,
            depths=depths_str,
            runs=spec.command_vars["runs"],
            warmup=spec.command_vars["warmup"],
            output=output_file,
        )

        result = runner.run(
            command,
            timeout_sec=min(spec.timeout_sec, runner.remaining_budget()),
            capture_output=True,
        )

        raw: dict[str, Any] = {
            "exit_code": result.exit_code,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
            "timed_out": result.status == "timeout",
            "output_file": output_file,
        }

        # Parse JSON output if file exists
        if os.path.exists(output_file):
            try:
                with open(output_file) as f:
                    raw["json"] = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                raw["parse_error"] = str(e)

        return raw

    def parse(self, raw: dict[str, Any], spec: BenchmarkSpec) -> BenchmarkResult:
        # Timeout or failure → no 0 TPS stored
        if raw.get("timed_out"):
            return BenchmarkResult(
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.TIMEOUT,
                error=FailureInfo(error_class="timeout", message="llama-benchy timed out"),
            )

        if raw.get("exit_code") != 0:
            return BenchmarkResult(
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error=FailureInfo(
                    error_class="process_failure",
                    message=f"llama-benchy exit code {raw.get('exit_code')}: {raw.get('stderr', '')[-500:]}",
                ),
            )

        data = raw.get("json")
        if not data or "parse_error" in raw:
            return BenchmarkResult(
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error=FailureInfo(
                    error_class="parse_error",
                    message=raw.get("parse_error", "no JSON output"),
                ),
            )

        benchmarks = data.get("benchmarks", [])
        if not benchmarks:
            return BenchmarkResult(
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error=FailureInfo(error_class="empty_results", message="no benchmarks in output"),
            )

        # Parse each depth result
        task_results = []
        valid_pp: list[float] = []
        valid_tg: list[float] = []

        for bench in benchmarks:
            ctx = bench.get("context_size", 0)
            pp_mean = bench.get("pp_throughput", {}).get("mean")
            tg_mean = bench.get("tg_throughput", {}).get("mean")

            # Validate: reject NaN, None, negative, zero
            pp_valid = self._validate_metric(pp_mean)
            tg_valid = self._validate_metric(tg_mean)

            if not (pp_valid or tg_valid):
                task_results.append(TaskResult(
                    task_id=f"depth-{ctx}",
                    status=RunStatus.FAILED,
                    error=FailureInfo(
                        error_class="invalid_metrics",
                        message=f"no valid throughput at ctx={ctx} (pp={pp_mean}, tg={tg_mean})",
                    ),
                ))
                continue

            if pp_valid:
                valid_pp.append(pp_mean)
            if tg_valid:
                valid_tg.append(tg_mean)

            task_results.append(TaskResult(
                task_id=f"depth-{ctx}",
                status=RunStatus.COMPLETED,
                raw_score=tg_mean if tg_valid else None,
                normalized_score=None,
                metadata={
                    "context_size": ctx,
                    "pp_throughput_mean": pp_mean if pp_valid else None,
                    "tg_throughput_mean": tg_mean if tg_valid else None,
                    "prompt_size": bench.get("prompt_size"),
                    "response_size": bench.get("response_size"),
                },
            ))

        # Overall: use highest context TG throughput as primary score
        if not valid_tg:
            return BenchmarkResult(
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error=FailureInfo(error_class="no_valid_tps", message="no valid TG throughput found"),
                task_results=task_results,
            )

        # Use the result at the deepest context as primary (matches V0.2 @64k convention)
        best_ctx = max(b.get("context_size", 0) for b in benchmarks if self._validate_metric(b.get("tg_throughput", {}).get("mean")))
        primary_tg = next(
            b["tg_throughput"]["mean"]
            for b in benchmarks
            if b.get("context_size") == best_ctx and self._validate_metric(b.get("tg_throughput", {}).get("mean"))
        )

        return BenchmarkResult(
            benchmark_name=self.name,
            benchmark_version=self.version,
            adapter_version=self.version,
            status=RunStatus.COMPLETED,
            raw_score=primary_tg,
            normalized_score=None,
            task_results=task_results,
            metadata={
                "pp_throughput_mean": sum(valid_pp) / len(valid_pp) if valid_pp else None,
                "tg_throughput_mean": primary_tg,
                "tg_throughput_avg_all": sum(valid_tg) / len(valid_tg),
                "valid_measurements": len(valid_tg),
                "total_benchmarks": len(benchmarks),
                "primary_context": best_ctx,
            },
            artifacts=[
                ArtifactRef(path=raw.get("output_file", ""))
            ],
        )

    @staticmethod
    def _validate_metric(value: Any) -> bool:
        """Reject None, NaN, negative, zero, and non-numeric values."""
        if value is None:
            return False
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False
        if math.isnan(v) or math.isinf(v):
            return False
        return v > 0
