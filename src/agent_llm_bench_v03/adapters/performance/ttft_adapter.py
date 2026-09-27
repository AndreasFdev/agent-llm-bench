"""TTFT (Time To First Token) adapter for V0.3.

Measures latency from HTTP request to first received token at multiple
prompt lengths using streaming API calls. Self-contained — no external script.
"""

from __future__ import annotations

import json
import math
import time
import urllib.request
import urllib.error
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


class TTFTAdapter(BenchmarkAdapter):
    """Measures Time To First Token at multiple prompt lengths.

    Quick profile: 512, 1024 tokens, 2 runs each (~1 min).
    Full profile: 512, 1024, 2048 tokens, 3 runs each.
    """

    name = "ttft"
    version = "1.0"
    category = "performance"
    timeout_sec = 180

    def __init__(self, timeout_per_request: int = 60):
        self.timeout_per_request = timeout_per_request

    def prepare(self, suite_run: SuiteRun, config: dict[str, Any]) -> BenchmarkSpec:
        profile = config.get("profile", "quick")
        if profile == "quick":
            lengths = [512, 1024]
            runs = 2
        else:
            lengths = [512, 1024, 2048]
            runs = 3

        return BenchmarkSpec(
            name=self.name,
            version=self.version,
            category=self.category,
            task_ids=[f"len-{l}" for l in lengths],
            timeout_sec=self.timeout_sec,
            command_vars={"lengths": lengths, "runs": runs},
        )

    def validate(self, spec: BenchmarkSpec) -> None:
        pass  # No external dependencies to check

    def execute(
        self,
        spec: BenchmarkSpec,
        runner: ProcessRunner,
        env: dict[str, str],
    ) -> dict[str, Any]:
        base_url = env.get("BENCH_BASE_URL", "")
        api_key = env.get("BENCH_API_KEY", "")
        model = env.get("BENCH_MODEL", "default")

        if not base_url:
            return {"error": "BENCH_BASE_URL not set"}

        lengths = spec.command_vars["lengths"]
        runs = spec.command_vars["runs"]

        results = []
        for length in lengths:
            length_results = []
            for run_idx in range(runs):
                prompt = self._build_prompt(length)
                ttft_s = self._measure_ttft(base_url, api_key, model, prompt)
                length_results.append(ttft_s)
            results.append({
                "prompt_length": length,
                "ttft_values_s": length_results,
            })

        return {"results": results}

    def parse(self, raw: dict[str, Any], spec: BenchmarkSpec) -> BenchmarkResult:
        if "error" in raw:
            return BenchmarkResult(
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error=FailureInfo(error_class="config_error", message=raw["error"]),
            )

        results = raw.get("results", [])
        if not results:
            return BenchmarkResult(
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error=FailureInfo(error_class="empty_results", message="no TTFT results"),
            )

        task_results = []
        all_valid: list[float] = []

        for r in results:
            length = r["prompt_length"]
            values = r["ttft_values_s"]

            # Filter out None (failed requests) and invalid values
            valid = [v for v in values if self._validate_ttft(v)]
            if not valid:
                task_results.append(TaskResult(
                    task_id=f"len-{length}",
                    status=RunStatus.FAILED,
                    error=FailureInfo(
                        error_class="no_valid_measurements",
                        message=f"no valid TTFT at length {length} (values={values})",
                    ),
                ))
                continue

            mean_ttft_s = sum(valid) / len(valid)
            all_valid.extend(valid)

            task_results.append(TaskResult(
                task_id=f"len-{length}",
                status=RunStatus.COMPLETED,
                raw_score=mean_ttft_s * 1000,  # ms for consistency with V0.2
                metadata={
                    "prompt_length": length,
                    "ttft_mean_ms": mean_ttft_s * 1000,
                    "ttft_values_ms": [v * 1000 for v in valid],
                    "valid_runs": len(valid),
                    "total_runs": len(values),
                },
            ))

        if not all_valid:
            return BenchmarkResult(
                benchmark_name=self.name,
                benchmark_version=self.version,
                adapter_version=self.version,
                status=RunStatus.FAILED,
                error=FailureInfo(error_class="no_valid_tps", message="no valid TTFT measurements"),
                task_results=task_results,
            )

        # Overall: average across all lengths (matches V0.2 ttft_overall_avg_s)
        overall_mean_ms = sum(all_valid) / len(all_valid) * 1000

        return BenchmarkResult(
            benchmark_name=self.name,
            benchmark_version=self.version,
            adapter_version=self.version,
            status=RunStatus.COMPLETED,
            raw_score=overall_mean_ms,
            task_results=task_results,
            metadata={
                "ttft_overall_avg_ms": overall_mean_ms,
                "valid_measurements": len(all_valid),
                "prompt_lengths": [r["prompt_length"] for r in results],
            },
        )

    @staticmethod
    def _build_prompt(target_tokens: int) -> str:
        """Build a neutral prompt of approximately target_tokens tokens."""
        sentence = (
            "The quick brown fox jumps over the lazy dog near the river bank "
            "on a sunny afternoon while birds sing in the trees above."
        )
        target_chars = target_tokens * 4
        num_repeats = max(1, target_chars // len(sentence))
        prompt_body = " ".join([sentence] * num_repeats)
        return f"{prompt_body}\n\nQuestion: What is the main subject of this text?"

    def _measure_ttft(self, base_url: str, api_key: str, model: str, prompt: str) -> Optional[float]:
        """Measure TTFT for a single streaming request. Returns seconds or None."""
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "max_tokens": 50,
            "temperature": 0.0,
        }

        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_per_request) as response:
                for line in response:
                    if not line:
                        continue
                    line_str = line.decode("utf-8").strip()
                    if not line_str.startswith("data: "):
                        continue
                    data = line_str[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                return time.time() - start_time
                    except json.JSONDecodeError:
                        continue
                # Stream ended without content token
                return None
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            return None

    @staticmethod
    def _validate_ttft(value: Any) -> bool:
        """Reject None, NaN, negative, zero."""
        if value is None:
            return False
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False
        if math.isnan(v) or math.isinf(v):
            return False
        return v > 0
