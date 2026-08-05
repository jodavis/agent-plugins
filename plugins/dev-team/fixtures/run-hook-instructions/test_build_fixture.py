"""Tests for build_fixture.py — confirms each of the three named dry-run scenarios for the
run-hook-instructions harness actually produces the fixture git repo and `instructions` map
state it claims to, so a dry run of the skill always starts from a trustworthy, reproducible
starting state.
"""

import subprocess
from pathlib import Path

import pytest

from build_fixture import (
    SCENARIOS,
    build_commit_entry_scenario,
    build_disabled_entry_scenario,
    build_scenario,
    build_unrecognized_instruction_scenario,
)


def _has_uncommitted_changes(work: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=work, capture_output=True, text=True, timeout=15
    )
    return bool(result.stdout.strip())


def _commit_count(work: Path) -> int:
    result = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=work, capture_output=True, text=True, timeout=15
    )
    return int(result.stdout.strip())


# ---------------------------------------------------------------------------
# build_commit_entry_scenario
# ---------------------------------------------------------------------------

class TestBuildCommitEntryScenario:
    def test_build_commit_entry_scenario_leaves_uncommitted_changes(self, tmp_path):
        # Arrange / Act
        fixture = build_commit_entry_scenario(tmp_path)

        # Assert
        assert _has_uncommitted_changes(fixture.worktree)

    def test_build_commit_entry_scenario_starts_with_exactly_one_commit(self, tmp_path):
        # Arrange / Act
        fixture = build_commit_entry_scenario(tmp_path)

        # Assert
        assert _commit_count(fixture.worktree) == 1

    def test_build_commit_entry_scenario_instruction_is_non_empty(self, tmp_path):
        # Arrange / Act
        fixture = build_commit_entry_scenario(tmp_path)

        # Assert
        assert fixture.instructions["commit-uncommitted"] == "Commit any uncommitted changes"

    def test_build_commit_entry_scenario_expects_successful_with_new_commit(self, tmp_path):
        # Arrange / Act
        fixture = build_commit_entry_scenario(tmp_path)

        # Assert
        assert fixture.expected_outcome == "successful"
        assert fixture.expected_commit_created is True


# ---------------------------------------------------------------------------
# build_disabled_entry_scenario
# ---------------------------------------------------------------------------

class TestBuildDisabledEntryScenario:
    def test_build_disabled_entry_scenario_leaves_uncommitted_changes(self, tmp_path):
        # Arrange / Act
        fixture = build_disabled_entry_scenario(tmp_path)

        # Assert
        assert _has_uncommitted_changes(fixture.worktree)

    def test_build_disabled_entry_scenario_instruction_is_disabled(self, tmp_path):
        # Arrange / Act
        fixture = build_disabled_entry_scenario(tmp_path)

        # Assert
        assert fixture.instructions["commit-uncommitted"] == ""

    def test_build_disabled_entry_scenario_expects_successful_with_no_new_commit(self, tmp_path):
        # Arrange / Act
        fixture = build_disabled_entry_scenario(tmp_path)

        # Assert
        assert fixture.expected_outcome == "successful"
        assert fixture.expected_commit_created is False


# ---------------------------------------------------------------------------
# build_unrecognized_instruction_scenario
# ---------------------------------------------------------------------------

class TestBuildUnrecognizedInstructionScenario:
    def test_build_unrecognized_instruction_scenario_instruction_has_no_obvious_operation(
        self, tmp_path
    ):
        # Arrange / Act
        fixture = build_unrecognized_instruction_scenario(tmp_path)

        # Assert
        assert fixture.instructions["recite-hamlet"] == "Recite three lines from Hamlet"

    def test_build_unrecognized_instruction_scenario_expects_failed_outcome(self, tmp_path):
        # Arrange / Act
        fixture = build_unrecognized_instruction_scenario(tmp_path)

        # Assert
        assert fixture.expected_outcome == "failed"
        assert fixture.expected_commit_created is False


# ---------------------------------------------------------------------------
# build_scenario — dispatch
# ---------------------------------------------------------------------------

class TestBuildScenarioDispatch:
    @pytest.mark.parametrize("name", SCENARIOS)
    def test_build_scenario_dispatches_to_the_matching_builder(self, tmp_path, name):
        # Arrange / Act
        fixture = build_scenario(name, tmp_path / name)

        # Assert
        assert fixture.context_file.exists()
        assert fixture.worktree.exists()

    def test_build_scenario_unknown_name_raises_value_error(self, tmp_path):
        # Arrange / Act / Assert
        with pytest.raises(ValueError):
            build_scenario("not-a-real-scenario", tmp_path)
