"""Tests for build_fixture.py — confirms each of the four named target/scenario combinations for
the workflow-worker / workflow-script `--event` dry-run harness actually produces the fixture git
repo, context-file `instructions` map, and CLI argument string it claims to, so a dry run of
either target skill always starts from a trustworthy, reproducible starting state.
"""

import json
import subprocess
from pathlib import Path

import pytest

from build_fixture import (
    SCENARIOS,
    TARGETS,
    DispatchFixture,
    build_fixture,
    build_script_scenario,
    build_worker_scenario,
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


def _read_instructions_map(fixture: DispatchFixture) -> dict:
    text = fixture.context_file.read_text()
    _, _, after_sentinel = text.partition("<!-- section:Project Configuration -->")
    config = json.loads(after_sentinel.strip())
    return config["instructions"]


# ---------------------------------------------------------------------------
# build_worker_scenario
# ---------------------------------------------------------------------------

class TestBuildWorkerScenario:
    def test_build_worker_scenario_with_event_leaves_uncommitted_changes(self, tmp_path):
        # Arrange / Act
        fixture = build_worker_scenario("with-event", tmp_path)

        # Assert
        assert _has_uncommitted_changes(fixture.worktree)

    def test_build_worker_scenario_starts_with_exactly_one_commit(self, tmp_path):
        # Arrange / Act
        fixture = build_worker_scenario("with-event", tmp_path)

        # Assert
        assert _commit_count(fixture.worktree) == 1

    def test_build_worker_scenario_with_event_includes_event_flag(self, tmp_path):
        # Arrange / Act
        fixture = build_worker_scenario("with-event", tmp_path)

        # Assert
        assert "--event fizzle" in fixture.cli_args
        assert "--skill get-project-configuration" in fixture.cli_args

    def test_build_worker_scenario_no_event_omits_event_flag(self, tmp_path):
        # Arrange / Act
        fixture = build_worker_scenario("no-event", tmp_path)

        # Assert
        assert "--event" not in fixture.cli_args

    def test_build_worker_scenario_no_event_still_carries_instructions_map(self, tmp_path):
        # Arrange / Act
        fixture = build_worker_scenario("no-event", tmp_path)

        # Assert
        instructions = _read_instructions_map(fixture)
        assert instructions["before-fizzle"]["commit-uncommitted"] == "Commit any uncommitted changes"
        assert instructions["after-fizzle"]["recite-hamlet"] == "Recite three lines from Hamlet"

    def test_build_worker_scenario_with_event_expects_failed_overall_result(self, tmp_path):
        # Arrange / Act
        fixture = build_worker_scenario("with-event", tmp_path)

        # Assert
        assert fixture.expected_overall_result_kind == "failed"
        assert fixture.expected_commit_count_after_run == 2

    def test_build_worker_scenario_no_event_expects_successful_overall_result(self, tmp_path):
        # Arrange / Act
        fixture = build_worker_scenario("no-event", tmp_path)

        # Assert
        assert fixture.expected_overall_result_kind == "successful"
        assert fixture.expected_commit_count_after_run == 1


# ---------------------------------------------------------------------------
# build_script_scenario
# ---------------------------------------------------------------------------

class TestBuildScriptScenario:
    def test_build_script_scenario_with_event_leaves_uncommitted_changes(self, tmp_path):
        # Arrange / Act
        fixture = build_script_scenario("with-event", tmp_path)

        # Assert
        assert _has_uncommitted_changes(fixture.worktree)

    def test_build_script_scenario_with_event_includes_event_flag(self, tmp_path):
        # Arrange / Act
        fixture = build_script_scenario("with-event", tmp_path)

        # Assert
        assert "--event fizzle" in fixture.cli_args
        assert "print(\'Succeeded\')" in fixture.cli_args

    def test_build_script_scenario_no_event_omits_event_flag(self, tmp_path):
        # Arrange / Act
        fixture = build_script_scenario("no-event", tmp_path)

        # Assert
        assert "--event" not in fixture.cli_args

    def test_build_script_scenario_with_event_expects_failed_overall_result(self, tmp_path):
        # Arrange / Act
        fixture = build_script_scenario("with-event", tmp_path)

        # Assert
        assert fixture.expected_overall_result_kind == "failed"
        assert fixture.expected_commit_count_after_run == 2

    def test_build_script_scenario_no_event_expects_successful_overall_result(self, tmp_path):
        # Arrange / Act
        fixture = build_script_scenario("no-event", tmp_path)

        # Assert
        assert fixture.expected_overall_result_kind == "successful"
        assert fixture.expected_commit_count_after_run == 1


# ---------------------------------------------------------------------------
# build_fixture — dispatch
# ---------------------------------------------------------------------------

class TestBuildFixtureDispatch:
    @pytest.mark.parametrize("target", TARGETS)
    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_build_fixture_dispatches_to_the_matching_builder(self, tmp_path, target, scenario):
        # Arrange / Act
        fixture = build_fixture(target, scenario, tmp_path / target / scenario)

        # Assert
        assert fixture.target == target
        assert fixture.scenario == scenario

    def test_build_fixture_unknown_target_raises_value_error(self, tmp_path):
        # Arrange / Act / Assert
        with pytest.raises(ValueError):
            build_fixture("not-a-real-target", "with-event", tmp_path)

    def test_build_fixture_unknown_scenario_raises_value_error(self, tmp_path):
        # Arrange / Act / Assert
        with pytest.raises(ValueError):
            build_fixture("worker", "not-a-real-scenario", tmp_path)
