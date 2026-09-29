"""Tests for build_fixture.py — confirms each of the two named dry-run scenarios for the
gather-pr-evidence harness actually produces the fixture worktree and PR-identity state it
claims to, so a dry run of the skill always starts from a trustworthy, reproducible starting
state. Neither scenario builder makes a network call — the real PR each scenario points at is
only fetched later, during the live dry run itself (see RUN.md), not by this test module.
"""

from pathlib import Path

import pytest

from build_fixture import (
    SCENARIOS,
    build_no_related_items_scenario,
    build_scenario,
    build_with_related_items_scenario,
)


def _read_config_text(worktree: Path) -> str:
    return (worktree / ".dev-team" / "config.yaml").read_text()


# ---------------------------------------------------------------------------
# build_with_related_items_scenario
# ---------------------------------------------------------------------------

class TestBuildWithRelatedItemsScenario:
    def test_build_with_related_items_scenario_creates_git_repo(self, tmp_path):
        # Arrange / Act
        fixture = build_with_related_items_scenario(tmp_path)

        # Assert
        assert (fixture.worktree / ".git").is_dir()

    def test_build_with_related_items_scenario_writes_both_provider_patterns(self, tmp_path):
        # Arrange / Act
        fixture = build_with_related_items_scenario(tmp_path)

        # Assert
        config_text = _read_config_text(fixture.worktree)
        assert "ADR-" in config_text
        assert "Issue-" in config_text

    def test_build_with_related_items_scenario_pr_identity_is_correct(self, tmp_path):
        # Arrange / Act
        fixture = build_with_related_items_scenario(tmp_path)

        # Assert
        assert fixture.pr_owner == "jodavis"
        assert fixture.pr_repo == "agent-plugins"
        assert fixture.pr_number == 103
        assert fixture.pr_ref == "jodavis/agent-plugins#103"

    def test_build_with_related_items_scenario_expects_both_providers_non_empty(self, tmp_path):
        # Arrange / Act
        fixture = build_with_related_items_scenario(tmp_path)

        # Assert
        assert fixture.expected_related_work_items_empty is False
        assert fixture.expected_provider_kinds == ["github", "jira"]


# ---------------------------------------------------------------------------
# build_no_related_items_scenario
# ---------------------------------------------------------------------------

class TestBuildNoRelatedItemsScenario:
    def test_build_no_related_items_scenario_creates_git_repo(self, tmp_path):
        # Arrange / Act
        fixture = build_no_related_items_scenario(tmp_path)

        # Assert
        assert (fixture.worktree / ".git").is_dir()

    def test_build_no_related_items_scenario_writes_both_provider_patterns(self, tmp_path):
        # Arrange / Act
        fixture = build_no_related_items_scenario(tmp_path)

        # Assert
        config_text = _read_config_text(fixture.worktree)
        assert "ADR-" in config_text
        assert "Issue-" in config_text

    def test_build_no_related_items_scenario_pr_identity_is_correct(self, tmp_path):
        # Arrange / Act
        fixture = build_no_related_items_scenario(tmp_path)

        # Assert
        assert fixture.pr_owner == "jodavis"
        assert fixture.pr_repo == "agent-plugins"
        assert fixture.pr_number == 230
        assert fixture.pr_ref == "jodavis/agent-plugins#230"

    def test_build_no_related_items_scenario_expects_empty_related_work_items(self, tmp_path):
        # Arrange / Act
        fixture = build_no_related_items_scenario(tmp_path)

        # Assert
        assert fixture.expected_related_work_items_empty is True
        assert fixture.expected_provider_kinds == []


# ---------------------------------------------------------------------------
# build_scenario — dispatch
# ---------------------------------------------------------------------------

class TestBuildScenarioDispatch:
    @pytest.mark.parametrize("name", SCENARIOS)
    def test_build_scenario_dispatches_to_the_matching_builder(self, tmp_path, name):
        # Arrange / Act
        fixture = build_scenario(name, tmp_path / name)

        # Assert
        assert fixture.worktree.exists()
        assert fixture.pr_ref.startswith("jodavis/agent-plugins#")

    def test_build_scenario_unknown_name_raises_value_error(self, tmp_path):
        # Arrange / Act / Assert
        with pytest.raises(ValueError):
            build_scenario("not-a-real-scenario", tmp_path)
