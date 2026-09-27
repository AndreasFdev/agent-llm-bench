"""Tests for suite profile definitions."""

import pytest

from agent_llm_bench_v03.suite.profiles import (
    PROFILE_QUICK,
    PROFILE_FULL,
    PROFILE_SMOKE,
    PROFILE_DEEP,
    PROFILES,
    get_profile,
)


class TestProfileDefinitions:
    """Test that profiles are correctly defined."""

    def test_smoke_profile(self):
        assert PROFILE_SMOKE.name == "smoke"
        assert PROFILE_SMOKE.budget_sec == 300
        assert len(PROFILE_SMOKE.adapters) >= 2

    def test_quick_profile(self):
        assert PROFILE_QUICK.name == "quick"
        assert PROFILE_QUICK.budget_sec == 1800
        # Quick should have all major categories
        categories = {a.category for a in PROFILE_QUICK.adapters}
        assert "performance" in categories
        assert "agentic" in categories
        assert "tool_calling" in categories
        assert "instruction_following" in categories

    def test_full_profile(self):
        assert PROFILE_FULL.name == "full"
        assert PROFILE_FULL.budget_sec >= 7200  # At least 2 hours
        # Full should have more budget than quick
        assert PROFILE_FULL.budget_sec > PROFILE_QUICK.budget_sec

    def test_deep_profile(self):
        assert PROFILE_DEEP.name == "deep"
        assert PROFILE_DEEP.budget_sec >= PROFILE_FULL.budget_sec

    def test_all_profiles_registered(self):
        assert "smoke" in PROFILES
        assert "quick" in PROFILES
        assert "full" in PROFILES
        assert "deep" in PROFILES


class TestGetProfile:
    """Test profile lookup."""

    def test_get_existing_profile(self):
        profile = get_profile("quick")
        assert profile.name == "quick"

    def test_get_nonexistent_profile(self):
        with pytest.raises(ValueError) as exc_info:
            get_profile("nonexistent")
        assert "Unknown profile" in str(exc_info.value)

    def test_profile_determinism(self):
        """Same profile should always return the same adapter configuration."""
        p1 = get_profile("quick")
        p2 = get_profile("quick")
        assert len(p1.adapters) == len(p2.adapters)
        for a1, a2 in zip(p1.adapters, p2.adapters):
            assert a1.adapter_class == a2.adapter_class
            assert a1.profile == a2.profile


class TestAdapterConfig:
    """Test adapter configuration within profiles."""

    def test_quick_adapter_timeouts_sum_within_budget(self):
        total_timeout = sum(a.timeout_sec for a in PROFILE_QUICK.adapters)
        # Sum of individual timeouts should be reasonable relative to budget
        assert total_timeout <= PROFILE_QUICK.budget_sec * 2

    def test_smoke_has_performance_adapters(self):
        adapter_classes = [a.adapter_class for a in PROFILE_SMOKE.adapters]
        assert "llama_benchy" in adapter_classes or "ttft" in adapter_classes

    def test_all_adapters_have_valid_profiles(self):
        for profile_name, profile in PROFILES.items():
            for adapter in profile.adapters:
                assert adapter.profile in ("quick", "full"), (
                    f"Invalid adapter profile '{adapter.profile}' "
                    f"in {profile_name}/{adapter.adapter_class}"
                )
