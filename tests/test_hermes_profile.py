import pytest

from merry_runtime.hermes_profile import (
    DANGEROUS_TOOLSETS,
    HermesProfileError,
    build_production_profile,
    validate_tool_lockdown,
)


def test_production_profile_disables_generic_dangerous_toolsets() -> None:
    profile = build_production_profile()

    assert DANGEROUS_TOOLSETS.issubset(profile["toolsets"].keys())
    assert all(profile["toolsets"][tool] is False for tool in DANGEROUS_TOOLSETS)
    assert profile["terminal"]["backend"] == "docker"
    assert profile["agent"]["max_turns"] <= 20
    assert profile["yolo"] is False


def test_tool_lockdown_rejects_enabled_terminal() -> None:
    profile = build_production_profile()
    profile["toolsets"]["terminal"] = True

    with pytest.raises(HermesProfileError):
        validate_tool_lockdown(profile)
