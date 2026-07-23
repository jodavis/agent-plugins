"""Tests for build_fixture.py — confirms each of the three named dry-run scenarios for the
resolve-rebase-conflict harness actually produces a real, deliberate rebase conflict (not a
clean rebase, and not the wrong set of conflicted files), so a dry run of the skill always
starts from a trustworthy, reproducible starting state.
"""

import subprocess
from pathlib import Path

import pytest

from build_fixture import (
    SCENARIOS,
    build_multi_file_scenario,
    build_scenario,
    build_single_file_scenario,
    build_unresolvable_scenario,
)


def _conflicted_paths(work: Path) -> set[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=15,
    )
    conflict_codes = {"UU", "AA", "DD", "AU", "UA", "UD", "DU"}
    paths = set()
    for line in result.stdout.splitlines():
        code, path = line[:2], line[3:]
        if code in conflict_codes:
            paths.add(path)
    return paths


def _rebase_in_progress(work: Path) -> bool:
    return (work / ".git" / "rebase-merge").exists() or (work / ".git" / "rebase-apply").exists()


# ---------------------------------------------------------------------------
# build_single_file_scenario
# ---------------------------------------------------------------------------

class TestBuildSingleFileScenario:
    def test_build_single_file_scenario_leaves_exactly_one_file_conflicted(self, tmp_path):
        # Arrange / Act
        fixture = build_single_file_scenario(tmp_path)

        # Assert
        assert _conflicted_paths(fixture.worktree) == {"CHANGELOG.md"}

    def test_build_single_file_scenario_leaves_rebase_in_progress(self, tmp_path):
        # Arrange / Act
        fixture = build_single_file_scenario(tmp_path)

        # Assert
        assert _rebase_in_progress(fixture.worktree)

    def test_build_single_file_scenario_reports_resolved_as_expected_outcome(self, tmp_path):
        # Arrange / Act
        fixture = build_single_file_scenario(tmp_path)

        # Assert
        assert fixture.expected_outcome == "resolved"

    def test_build_single_file_scenario_task_brief_names_its_own_changelog_entry(self, tmp_path):
        # Arrange / Act
        fixture = build_single_file_scenario(tmp_path)

        # Assert
        assert "Add rebase conflict resolution skill" in fixture.task_brief


# ---------------------------------------------------------------------------
# build_multi_file_scenario
# ---------------------------------------------------------------------------

class TestBuildMultiFileScenario:
    def test_build_multi_file_scenario_leaves_exactly_two_files_conflicted(self, tmp_path):
        # Arrange / Act
        fixture = build_multi_file_scenario(tmp_path)

        # Assert
        assert _conflicted_paths(fixture.worktree) == {"CHANGELOG.md", "config/settings.json"}

    def test_build_multi_file_scenario_leaves_rebase_in_progress(self, tmp_path):
        # Arrange / Act
        fixture = build_multi_file_scenario(tmp_path)

        # Assert
        assert _rebase_in_progress(fixture.worktree)

    def test_build_multi_file_scenario_reports_resolved_as_expected_outcome(self, tmp_path):
        # Arrange / Act
        fixture = build_multi_file_scenario(tmp_path)

        # Assert
        assert fixture.expected_outcome == "resolved"

    def test_build_multi_file_scenario_task_brief_states_max_retries_target(self, tmp_path):
        # Arrange / Act
        fixture = build_multi_file_scenario(tmp_path)

        # Assert
        assert "max_retries" in fixture.task_brief
        assert "5" in fixture.task_brief


# ---------------------------------------------------------------------------
# build_unresolvable_scenario
# ---------------------------------------------------------------------------

class TestBuildUnresolvableScenario:
    def test_build_unresolvable_scenario_leaves_exactly_one_file_conflicted(self, tmp_path):
        # Arrange / Act
        fixture = build_unresolvable_scenario(tmp_path)

        # Assert
        assert _conflicted_paths(fixture.worktree) == {"config/retry_policy.json"}

    def test_build_unresolvable_scenario_leaves_rebase_in_progress(self, tmp_path):
        # Arrange / Act
        fixture = build_unresolvable_scenario(tmp_path)

        # Assert
        assert _rebase_in_progress(fixture.worktree)

    def test_build_unresolvable_scenario_reports_unresolved_as_expected_outcome(self, tmp_path):
        # Arrange / Act
        fixture = build_unresolvable_scenario(tmp_path)

        # Assert
        assert fixture.expected_outcome == "unresolved"

    def test_build_unresolvable_scenario_task_brief_omits_a_target_value(self, tmp_path):
        # Arrange / Act
        fixture = build_unresolvable_scenario(tmp_path)

        # Assert
        assert "2.5" not in fixture.task_brief
        assert "2.0" not in fixture.task_brief


# ---------------------------------------------------------------------------
# build_scenario — dispatch
# ---------------------------------------------------------------------------

class TestBuildScenarioDispatch:
    @pytest.mark.parametrize("name", SCENARIOS)
    def test_build_scenario_dispatches_to_the_matching_builder(self, tmp_path, name):
        # Arrange / Act
        fixture = build_scenario(name, tmp_path / name)

        # Assert
        assert _rebase_in_progress(fixture.worktree)

    def test_build_scenario_unknown_name_raises_value_error(self, tmp_path):
        # Arrange / Act / Assert
        with pytest.raises(ValueError):
            build_scenario("not-a-real-scenario", tmp_path)


# ---------------------------------------------------------------------------
# Scenario content sanity: conflicting sides really do differ (the harness would be
# meaningless if a scenario's two branches happened to converge on the same content).
# ---------------------------------------------------------------------------

class TestScenarioConflictSidesDiffer:
    def test_multi_file_scenario_settings_conflict_sides_differ(self, tmp_path):
        # Arrange / Act
        fixture = build_multi_file_scenario(tmp_path)
        conflicted = (fixture.worktree / "config" / "settings.json").read_text()

        # Assert: both branches' distinct values are present as raw conflict markers —
        # nothing has been silently resolved by the builder itself.
        assert "<<<<<<<" in conflicted
        assert '"max_retries": 5' in conflicted
        assert '"max_retries": 4' in conflicted

    def test_unresolvable_scenario_retry_policy_conflict_sides_differ(self, tmp_path):
        # Arrange / Act
        fixture = build_unresolvable_scenario(tmp_path)
        conflicted = (fixture.worktree / "config" / "retry_policy.json").read_text()

        # Assert
        assert "<<<<<<<" in conflicted
        assert "2.5" in conflicted
        assert "2.0" in conflicted
