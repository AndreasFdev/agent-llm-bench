"""Core domain models for Agent LLM Bench V0.3.

Defines the stable contract between suite runner, adapters, and storage.
All models are serializable to/from JSON with schema versioning.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

from agent_llm_bench_v03.domain.status import RunStatus

SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ArtifactRef:
    """Reference to a stored artifact (file on disk)."""

    path: str  # relative path from artifact root
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    mime_type: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "ArtifactRef":
        return cls(**data)


@dataclass
class FailureInfo:
    """Structured failure information."""

    error_class: str  # e.g. "timeout", "http_error", "parse_error"
    message: str
    details: Optional[dict] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "FailureInfo":
        return cls(**data)


@dataclass
class TaskResult:
    """Result of a single task within a benchmark."""

    task_id: str
    status: RunStatus
    raw_score: Optional[float] = None
    normalized_score: Optional[float] = None
    duration_sec: Optional[float] = None
    ttft_sec: Optional[float] = None
    tps: Optional[float] = None
    error: Optional[FailureInfo] = None
    validator_version: Optional[str] = None
    prompt_artifact: Optional[ArtifactRef] = None
    response_artifact: Optional[ArtifactRef] = None
    log_artifact: Optional[ArtifactRef] = None
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        # Serialize nested objects
        if self.error:
            d["error"] = self.error.to_dict()
        if self.prompt_artifact:
            d["prompt_artifact"] = self.prompt_artifact.to_dict()
        if self.response_artifact:
            d["response_artifact"] = self.response_artifact.to_dict()
        if self.log_artifact:
            d["log_artifact"] = self.log_artifact.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TaskResult":
        # Deserialize nested objects
        if "error" in data and data["error"]:
            data["error"] = FailureInfo.from_dict(data["error"])
        if "prompt_artifact" in data and data["prompt_artifact"]:
            data["prompt_artifact"] = ArtifactRef.from_dict(data["prompt_artifact"])
        if "response_artifact" in data and data["response_artifact"]:
            data["response_artifact"] = ArtifactRef.from_dict(data["response_artifact"])
        if "log_artifact" in data and data["log_artifact"]:
            data["log_artifact"] = ArtifactRef.from_dict(data["log_artifact"])
        # Convert status string to enum
        if isinstance(data.get("status"), str):
            data["status"] = RunStatus(data["status"])
        return cls(**data)


@dataclass
class BenchmarkResult:
    """Canonical result of a benchmark adapter run."""

    schema_version: str = SCHEMA_VERSION
    benchmark_name: str = ""
    benchmark_version: str = ""
    adapter_version: str = ""
    status: RunStatus = RunStatus.QUEUED
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_sec: Optional[float] = None
    raw_score: Optional[float] = None
    normalized_score: Optional[float] = None
    capability_score: Optional[float] = None
    efficiency_score: Optional[float] = None
    task_results: list[TaskResult] = field(default_factory=list)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    error: Optional[FailureInfo] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        d["status"] = self.status.value
        if self.error:
            d["error"] = self.error.to_dict()
        d["task_results"] = [tr.to_dict() for tr in self.task_results]
        d["artifacts"] = [a.to_dict() for a in self.artifacts]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BenchmarkResult":
        if isinstance(data.get("status"), str):
            data["status"] = RunStatus(data["status"])
        if "error" in data and data["error"]:
            data["error"] = FailureInfo.from_dict(data["error"])
        data["task_results"] = [TaskResult.from_dict(tr) for tr in data.get("task_results", [])]
        data["artifacts"] = [ArtifactRef.from_dict(a) for a in data.get("artifacts", [])]
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


@dataclass
class BenchmarkSpec:
    """Specification of a benchmark adapter to run."""

    name: str
    version: str
    category: str  # "performance", "agentic", "tool_calling", "coding", "instruction"
    profiles: list[str] = field(default_factory=list)  # which profiles include this
    task_ids: list[str] = field(default_factory=list)  # empty = all tasks
    selection_strategy: str = "fixed"  # "fixed", "random_seed", "adaptive"
    command_template: str = ""  # shell command or python callable path
    command_vars: dict[str, Any] = field(default_factory=dict)  # variables for command template
    expected_artifacts: list[str] = field(default_factory=list)
    timeout_sec: int = 300
    budget_sec: Optional[int] = None  # target budget within suite
    prerequisites: list[str] = field(default_factory=list)  # other benchmarks that must run first

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BenchmarkSpec":
        return cls(**data)


@dataclass
class SuiteProfile:
    """Definition of a benchmark suite profile (smoke, quick, full, deep)."""

    name: str
    version: str
    description: str = ""
    budget_sec: int = 2400
    benchmarks: list[BenchmarkSpec] = field(default_factory=list)
    manifest_hash: Optional[str] = None  # computed from benchmarks + task selection

    def compute_manifest_hash(self) -> str:
        """Compute deterministic hash of the suite configuration."""
        content = json.dumps({
            "name": self.name,
            "version": self.version,
            "budget_sec": self.budget_sec,
            "benchmarks": [b.to_dict() for b in self.benchmarks],
        }, sort_keys=True)
        return _sha256(content)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["benchmarks"] = [b.to_dict() for b in self.benchmarks]
        return d


@dataclass
class SuiteRun:
    """A single execution of a suite profile."""

    suite_run_id: str
    profile_name: str
    profile_version: str
    model_name: str
    node_id: str
    status: RunStatus = RunStatus.QUEUED
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_duration_sec: Optional[float] = None
    manifest_hash: Optional[str] = None
    config_hash: Optional[str] = None
    reproducibility_hash: Optional[str] = None
    error: Optional[FailureInfo] = None

    def to_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        d["status"] = self.status.value
        if self.error:
            d["error"] = self.error.to_dict()
        return d


@dataclass
class BenchmarkRun:
    """A single execution of a benchmark within a suite run."""

    run_id: int
    suite_run_id: str
    benchmark_name: str
    benchmark_version: str
    adapter_version: str
    model_name: str
    node_id: str
    variant: Optional[str] = None  # e.g. "n_ctx=64000,batch_size=512"
    status: RunStatus = RunStatus.QUEUED
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_sec: Optional[float] = None
    result: Optional[BenchmarkResult] = None
    config_json: Optional[dict] = None

    def to_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        d["status"] = self.status.value
        if self.result:
            d["result"] = self.result.to_dict()
        return d


@dataclass
class Manifest:
    """Immutable run manifest for reproducibility."""

    schema_version: str = SCHEMA_VERSION
    suite_level: str = ""  # "smoke", "quick", "full", "deep"
    suite_version: str = ""
    task_set_version: str = ""
    task_ids: list[str] = field(default_factory=list)
    task_hash: Optional[str] = None
    seed: int = 42
    adapter_versions: dict[str, str] = field(default_factory=dict)
    external_repo_shas: dict[str, str] = field(default_factory=dict)
    scorer_versions: dict[str, str] = field(default_factory=dict)
    model_name: str = ""
    gguf_hash: Optional[str] = None
    node_id: str = ""
    endpoint_type: str = ""
    effective_params: dict[str, Any] = field(default_factory=dict)
    sampling_config: dict[str, Any] = field(default_factory=dict)
    context_config: dict[str, Any] = field(default_factory=dict)
    timeout_sec: int = 300
    budget_sec: int = 2400
    created_at: str = field(default_factory=_now_iso)

    def compute_task_hash(self) -> str:
        """Hash of the task selection."""
        content = json.dumps({
            "task_ids": sorted(self.task_ids),
            "seed": self.seed,
            "task_set_version": self.task_set_version,
        }, sort_keys=True)
        return _sha256(content)

    def compute_config_hash(self) -> str:
        """Hash of the effective configuration."""
        content = json.dumps({
            "model_name": self.model_name,
            "effective_params": self.effective_params,
            "sampling_config": self.sampling_config,
            "context_config": self.context_config,
            "timeout_sec": self.timeout_sec,
            "budget_sec": self.budget_sec,
        }, sort_keys=True)
        return _sha256(content)

    def compute_reproducibility_hash(self) -> str:
        """Complete reproducibility hash."""
        self.task_hash = self.compute_task_hash()
        config_hash = self.compute_config_hash()
        content = json.dumps({
            "schema_version": self.schema_version,
            "suite_level": self.suite_level,
            "suite_version": self.suite_version,
            "task_hash": self.task_hash,
            "config_hash": config_hash,
            "adapter_versions": self.adapter_versions,
            "external_repo_shas": self.external_repo_shas,
            "scorer_versions": self.scorer_versions,
        }, sort_keys=True)
        return _sha256(content)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)
