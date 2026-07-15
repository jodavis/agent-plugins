"""Tests for task_dependencies.py — parse_task_dependencies(), which turns a spec's
already-rewritten `## Tasks` section (every `Depends on:` reference already a real
task-work-item key) into a `{task_key: [dependency_keys]}` dependency graph.

Covers:
- No `Depends on:` line present for a task (defaults to no dependencies)
- A single dependency
- Multiple (comma-separated) dependencies
- An explicit `**Depends on:** — none —` line amid other tasks that do have dependencies
- A dangling reference (a `Depends on:` entry naming a task not present in the spec)
- A two-task and a three-task dependency cycle
"""

import pytest


# ---------------------------------------------------------------------------
# parse_task_dependencies — dependency-free tasks
# ---------------------------------------------------------------------------

class TestParseTaskDependenciesNoDependencies:
    def test_parse_task_dependencies_spec_with_no_task_headings_returns_empty_graph(self):
        # Arrange
        from task_dependencies import parse_task_dependencies
        spec_text = "## Tasks\n\nNo tasks have been drafted yet.\n"

        # Act
        graph = parse_task_dependencies(spec_text)

        # Assert
        assert graph == {}

    def test_parse_task_dependencies_task_with_no_depends_on_line_returns_empty_list(self):
        # Arrange
        from task_dependencies import parse_task_dependencies
        spec_text = (
            "### [ADR-1: Solo task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "A task with no Depends on: line at all.\n"
        )

        # Act
        graph = parse_task_dependencies(spec_text)

        # Assert
        assert graph == {"ADR-1": []}

    def test_parse_task_dependencies_task_with_none_declared_amid_other_tasks_returns_empty_list_for_that_task(self):
        # Arrange
        from task_dependencies import parse_task_dependencies
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** — none —\n\n"
            "A task with an explicit none.\n\n"
            "### [ADR-2: Second task](https://jodasoft.atlassian.net/browse/ADR-2) 🤖\n\n"
            "**Depends on:** ADR-1\n\n"
            "A task that depends on the first.\n"
        )

        # Act
        graph = parse_task_dependencies(spec_text)

        # Assert
        assert graph == {"ADR-1": [], "ADR-2": ["ADR-1"]}


# ---------------------------------------------------------------------------
# parse_task_dependencies — declared dependencies
# ---------------------------------------------------------------------------

class TestParseTaskDependenciesDeclaredDependencies:
    def test_parse_task_dependencies_single_dependency_returns_task_with_one_dependency(self):
        # Arrange
        from task_dependencies import parse_task_dependencies
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** — none —\n\n"
            "### [ADR-2: Second task](https://jodasoft.atlassian.net/browse/ADR-2) 🤖\n\n"
            "**Depends on:** ADR-1\n\n"
            "Builds on the first task.\n"
        )

        # Act
        graph = parse_task_dependencies(spec_text)

        # Assert
        assert graph["ADR-2"] == ["ADR-1"]

    def test_parse_task_dependencies_multiple_dependencies_returns_task_with_all_dependencies(self):
        # Arrange
        from task_dependencies import parse_task_dependencies
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** — none —\n\n"
            "### [ADR-2: Second task](https://jodasoft.atlassian.net/browse/ADR-2) 🤖\n\n"
            "**Depends on:** — none —\n\n"
            "### [ADR-3: Third task](https://jodasoft.atlassian.net/browse/ADR-3) 🤖\n\n"
            "**Depends on:** ADR-1, ADR-2\n\n"
            "Builds on both prior tasks.\n"
        )

        # Act
        graph = parse_task_dependencies(spec_text)

        # Assert
        assert graph["ADR-3"] == ["ADR-1", "ADR-2"]


# ---------------------------------------------------------------------------
# parse_task_dependencies — dangling reference
# ---------------------------------------------------------------------------

class TestParseTaskDependenciesDanglingReference:
    def test_parse_task_dependencies_dangling_reference_raises_error_naming_task_and_reference(self):
        # Arrange
        from task_dependencies import TaskDependencyError, parse_task_dependencies
        spec_text = (
            "### [ADR-1: Only task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** ADR-999\n\n"
            "Depends on a task that does not exist in this spec.\n"
        )

        # Act / Assert
        with pytest.raises(TaskDependencyError) as exc_info:
            parse_task_dependencies(spec_text)
        assert "ADR-1" in str(exc_info.value)
        assert "ADR-999" in str(exc_info.value)


# ---------------------------------------------------------------------------
# parse_task_dependencies — dependency cycles
# ---------------------------------------------------------------------------

class TestParseTaskDependenciesCycles:
    def test_parse_task_dependencies_two_task_cycle_raises_error_naming_cyclic_tasks(self):
        # Arrange
        from task_dependencies import TaskDependencyError, parse_task_dependencies
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** ADR-2\n\n"
            "### [ADR-2: Second task](https://jodasoft.atlassian.net/browse/ADR-2) 🤖\n\n"
            "**Depends on:** ADR-1\n\n"
        )

        # Act / Assert
        with pytest.raises(TaskDependencyError) as exc_info:
            parse_task_dependencies(spec_text)
        assert "ADR-1" in str(exc_info.value)
        assert "ADR-2" in str(exc_info.value)

    def test_parse_task_dependencies_three_task_cycle_raises_error_naming_cyclic_tasks(self):
        # Arrange
        from task_dependencies import TaskDependencyError, parse_task_dependencies
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** ADR-3\n\n"
            "### [ADR-2: Second task](https://jodasoft.atlassian.net/browse/ADR-2) 🤖\n\n"
            "**Depends on:** ADR-1\n\n"
            "### [ADR-3: Third task](https://jodasoft.atlassian.net/browse/ADR-3) 🤖\n\n"
            "**Depends on:** ADR-2\n\n"
        )

        # Act / Assert
        with pytest.raises(TaskDependencyError) as exc_info:
            parse_task_dependencies(spec_text)
        assert "ADR-1" in str(exc_info.value)
        assert "ADR-2" in str(exc_info.value)
        assert "ADR-3" in str(exc_info.value)
