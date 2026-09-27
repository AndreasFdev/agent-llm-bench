"""Benchmark suite profile definitions.

Profiles define which adapters run, with what settings, and under what time budget.
Deterministic: same profile always selects the same tasks (by ID order).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdapterConfig:
    """Configuration for a single adapter within a profile."""

    adapter_class: str  # Import path or registered name
    category: str
    profile: str = "quick"  # Passed to adapter's own profile param
    timeout_sec: int = 300
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuiteProfile:
    """Definition of a benchmark suite profile."""

    name: str
    version: str
    description: str
    budget_sec: int  # Total time budget for the entire suite
    adapters: list[AdapterConfig] = field(default_factory=list)

    def adapter_count(self) -> int:
        return len(self.adapters)


# ─── Profile Definitions ────────────────────────────────────────────────────

PROFILE_SMOKE = SuiteProfile(
    name="smoke",
    version="1.0.0",
    description="Sanity check: connectivity + basic performance (2-5 min)",
    budget_sec=300,
    adapters=[
        AdapterConfig("llama_benchy", "performance", profile="quick", timeout_sec=120),
        AdapterConfig("ttft", "performance", profile="quick", timeout_sec=60),
    ],
)

PROFILE_QUICK = SuiteProfile(
    name="quick",
    version="1.0.0",
    description="Fast comprehensive: performance + agentic + tool calling + instruction (20-30 min)",
    budget_sec=1800,  # 30 minutes
    adapters=[
        # Performance (4 min)
        AdapterConfig("llama_benchy", "performance", profile="quick", timeout_sec=120),
        AdapterConfig("ttft", "performance", profile="quick", timeout_sec=120),
        # Agentic coding (8 min)
        AdapterConfig("local_agent_benchmark", "agentic", profile="quick", timeout_sec=480),
        # Tool calling (5 min)
        AdapterConfig("bfcl_tool_calling", "tool_calling", profile="quick", timeout_sec=300),
        # Instruction following (4 min)
        AdapterConfig("instruction_following", "instruction_following", profile="quick", timeout_sec=240),
    ],
)

PROFILE_FULL = SuiteProfile(
    name="full",
    version="1.0.0",
    description="Complete benchmark: all categories, full task sets (2-4 hours)",
    budget_sec=14400,  # 4 hours
    adapters=[
        AdapterConfig("llama_benchy", "performance", profile="full", timeout_sec=300),
        AdapterConfig("ttft", "performance", profile="full", timeout_sec=300),
        AdapterConfig("local_agent_benchmark", "agentic", profile="full", timeout_sec=3600),
        AdapterConfig("bfcl_tool_calling", "tool_calling", profile="full", timeout_sec=1800),
        AdapterConfig("instruction_following", "instruction_following", profile="full", timeout_sec=1800),
    ],
)

PROFILE_DEEP = SuiteProfile(
    name="deep",
    version="1.0.0",
    description="Extended: full + stress tests + extended context (6+ hours)",
    budget_sec=28800,  # 8 hours
    adapters=[
        AdapterConfig("llama_benchy", "performance", profile="full", timeout_sec=600),
        AdapterConfig("ttft", "performance", profile="full", timeout_sec=300),
        AdapterConfig("local_agent_benchmark", "agentic", profile="full", timeout_sec=7200),
        AdapterConfig("bfcl_tool_calling", "tool_calling", profile="full", timeout_sec=3600),
        AdapterConfig("instruction_following", "instruction_following", profile="full", timeout_sec=3600),
    ],
)

PROFILES = {
    "smoke": PROFILE_SMOKE,
    "quick": PROFILE_QUICK,
    "full": PROFILE_FULL,
    "deep": PROFILE_DEEP,
}


def get_profile(name: str) -> SuiteProfile:
    """Get a profile by name."""
    if name not in PROFILES:
        raise ValueError(f"Unknown profile: {name}. Available: {list(PROFILES.keys())}")
    return PROFILES[name]
