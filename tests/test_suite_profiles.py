"""Tests for suite profile definitions."""

import pytest

from agent_llm_bench_v03.suite.profiles import (
    PROFILE_QUICK,
    PROFILE_SMOKE,
    AdapterConfig,
    SuiteProfile,
    get_profile,
)


class TestQuickProfile:
    """QUICK_PROFILE must match concept doc specification."""

    def test_name(self):
        assert PROFILE_QUICK.name == "quick"

    def test_budget(self):
        # 1800s = 30 minutes (concept doc: hard limit 40min)
        assert PROFILE_QUICK.budget_sec == 1800

    def test_adapter_count(self):
        # 5 adapters: llama_benchy, ttft, local_agent, bfcl, instruction
        assert len(PROFILE_QUICK.adapters) == 5

    def test_adapter_names(self):
        names = [a.adapter_class for a in PROFILE_QUICK.adapters]
        assert "llama_benchy" in names
        assert "ttft" in names
        assert "local_agent_benchmark" in names
        assert "bfcl_tool_calling" in names
        assert "instruction_following" in names

    def test_all_adapters_have_profile_quick(self):
        for a in PROFILE_QUICK.adapters:
            assert a.profile == "quick", f"{a.adapter_class} should use profile=quick"


class TestSmokeProfile:
    """SMOKE_PROFILE for fast validation."""

    def test_name(self):
        assert PROFILE_SMOKE.name == "smoke"

    def test_budget(self):
        assert PROFILE_SMOKE.budget_sec == 300  # 5 minutes

    def test_adapter_count(self):
        assert len(PROFILE_SMOKE.adapters) == 2


class TestGetProfile:
    """Profile lookup by name."""

    def test_get_quick(self):
        profile = get_profile("quick")
        assert profile.name == "quick"

    def test_get_smoke(self):
        profile = get_profile("smoke")
        assert profile.name == "smoke"

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            get_profile("nonexistent")


class TestAdapterConfig:
    """AdapterConfig dataclass."""

    def test_timeout_default(self):
        config = AdapterConfig(adapter_class="test", category="performance", params={})
        assert config.timeout_sec == 300

    def test_custom_timeout(self):
        config = AdapterConfig(
            adapter_class="test", category="performance", params={}, timeout_sec=600
        )
        assert config.timeout_sec == 600


class TestSuiteProfile:
    """SuiteProfile dataclass."""

    def test_adapter_count_method(self):
        profile = SuiteProfile(name="test", version="1.0.0", description="Test", budget_sec=100, adapters=[
            AdapterConfig(adapter_class="test", category="performance", params={})
        ])
        assert profile.adapter_count() == 1
