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


# ---------------------------------------------------------------------------
# validate_stack_order — valid order
# ---------------------------------------------------------------------------

class TestValidateStackOrder:
    def test_validate_stack_order_valid_order_returns_same_order_unchanged(self):
        # Arrange
        from task_dependencies import validate_stack_order
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** — none —\n\n"
            "### [ADR-2: Second task](https://jodasoft.atlassian.net/browse/ADR-2) 🤖\n\n"
            "**Depends on:** ADR-1\n\n"
            "### [ADR-3: Third task](https://jodasoft.atlassian.net/browse/ADR-3) 🤖\n\n"
            "**Depends on:** ADR-1, ADR-2\n\n"
        )

        # Act
        order = validate_stack_order(spec_text)

        # Assert
        assert order == ["ADR-1", "ADR-2", "ADR-3"]


# ---------------------------------------------------------------------------
# validate_stack_order — out-of-order pair
# ---------------------------------------------------------------------------

class TestValidateStackOrderOutOfOrder:
    def test_validate_stack_order_task_listed_before_its_dependency_raises_error_naming_both_tasks(self):
        # Arrange
        from task_dependencies import TaskDependencyError, validate_stack_order
        spec_text = (
            "### [ADR-2: Second task](https://jodasoft.atlassian.net/browse/ADR-2) 🤖\n\n"
            "**Depends on:** ADR-1\n\n"
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** — none —\n\n"
        )

        # Act / Assert
        with pytest.raises(TaskDependencyError) as exc_info:
            validate_stack_order(spec_text)
        assert "ADR-2" in str(exc_info.value)
        assert "ADR-1" in str(exc_info.value)


# ---------------------------------------------------------------------------
# validate_stack_order — dangling reference (re-tested through the new entry point)
# ---------------------------------------------------------------------------

class TestValidateStackOrderDanglingReference:
    def test_validate_stack_order_dangling_reference_raises_error_naming_task_and_reference(self):
        # Arrange
        from task_dependencies import TaskDependencyError, validate_stack_order
        spec_text = (
            "### [ADR-1: Only task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** ADR-999\n\n"
            "Depends on a task that does not exist in this spec.\n"
        )

        # Act / Assert
        with pytest.raises(TaskDependencyError) as exc_info:
            validate_stack_order(spec_text)
        assert "ADR-1" in str(exc_info.value)
        assert "ADR-999" in str(exc_info.value)


# ---------------------------------------------------------------------------
# parse_task_markers — human/agent marker extraction per task key
# ---------------------------------------------------------------------------

class TestParseTaskMarkers:
    def test_parse_task_markers_agent_heading_returns_agent_marker(self):
        # Arrange
        from task_dependencies import AGENT_MARKER, parse_task_markers
        spec_text = (
            "### [ADR-1: Solo task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** — none —\n"
        )

        # Act
        markers = parse_task_markers(spec_text)

        # Assert
        assert markers == {"ADR-1": AGENT_MARKER}

    def test_parse_task_markers_human_heading_returns_human_marker(self):
        # Arrange
        from task_dependencies import HUMAN_MARKER, parse_task_markers
        spec_text = (
            "### [ADR-1: Provision access](https://jodasoft.atlassian.net/browse/ADR-1) 🧑\n\n"
            "**Depends on:** — none —\n"
        )

        # Act
        markers = parse_task_markers(spec_text)

        # Assert
        assert markers == {"ADR-1": HUMAN_MARKER}

    def test_parse_task_markers_multiple_tasks_returns_marker_for_each(self):
        # Arrange
        from task_dependencies import AGENT_MARKER, HUMAN_MARKER, parse_task_markers
        spec_text = (
            "### [ADR-1: Provision access](https://jodasoft.atlassian.net/browse/ADR-1) 🧑\n\n"
            "**Depends on:** — none —\n\n"
            "### [ADR-2: Wire up client](https://jodasoft.atlassian.net/browse/ADR-2) 🤖\n\n"
            "**Depends on:** ADR-1\n"
        )

        # Act
        markers = parse_task_markers(spec_text)

        # Assert
        assert markers == {"ADR-1": HUMAN_MARKER, "ADR-2": AGENT_MARKER}

    def test_parse_task_markers_no_task_headings_returns_empty_dict(self):
        # Arrange
        from task_dependencies import parse_task_markers
        spec_text = "## Tasks\n\nNo tasks have been drafted yet.\n"

        # Act
        markers = parse_task_markers(spec_text)

        # Assert
        assert markers == {}


# ---------------------------------------------------------------------------
# validate_task_headings — a heading that looks like a task heading but is
# missing/malformed on its trailing 🤖/🧑 marker raises a clear error, naming it,
# instead of silently vanishing from the graph
# ---------------------------------------------------------------------------

class TestValidateTaskHeadings:
    def test_validate_task_headings_all_well_formed_does_not_raise(self):
        # Arrange
        from task_dependencies import validate_task_headings
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** — none —\n\n"
            "### [ADR-2: Second task](https://jodasoft.atlassian.net/browse/ADR-2) 🧑\n\n"
            "**Depends on:** ADR-1\n"
        )

        # Act / Assert — no exception
        validate_task_headings(spec_text)

    def test_validate_task_headings_no_candidate_headings_does_not_raise(self):
        # Arrange
        from task_dependencies import validate_task_headings
        spec_text = "## Tasks\n\nNo tasks have been drafted yet.\n"

        # Act / Assert — no exception
        validate_task_headings(spec_text)

    def test_validate_task_headings_missing_marker_raises_error_naming_heading(self):
        # Arrange
        from task_dependencies import TaskDependencyError, validate_task_headings
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1)\n\n"
            "**Depends on:** — none —\n"
        )

        # Act / Assert
        with pytest.raises(TaskDependencyError) as exc_info:
            validate_task_headings(spec_text)
        assert "ADR-1" in str(exc_info.value)

    def test_validate_task_headings_wrong_trailing_marker_raises_error_naming_heading(self):
        # Arrange — a stray character instead of one of the two required emoji
        from task_dependencies import TaskDependencyError, validate_task_headings
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) ?\n\n"
            "**Depends on:** — none —\n"
        )

        # Act / Assert
        with pytest.raises(TaskDependencyError) as exc_info:
            validate_task_headings(spec_text)
        assert "ADR-1" in str(exc_info.value)

    def test_validate_task_headings_one_malformed_among_well_formed_raises_naming_only_offender(self):
        # Arrange
        from task_dependencies import TaskDependencyError, validate_task_headings
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** — none —\n\n"
            "### [ADR-2: Second task](https://jodasoft.atlassian.net/browse/ADR-2)\n\n"
            "**Depends on:** ADR-1\n"
        )

        # Act / Assert
        with pytest.raises(TaskDependencyError) as exc_info:
            validate_task_headings(spec_text)
        assert "ADR-2" in str(exc_info.value)


# ---------------------------------------------------------------------------
# validate_stack_order — dependency cycles (re-tested through the new entry point)
# ---------------------------------------------------------------------------

class TestValidateStackOrderCycles:
    def test_validate_stack_order_two_task_cycle_raises_error_naming_cyclic_tasks(self):
        # Arrange
        from task_dependencies import TaskDependencyError, validate_stack_order
        spec_text = (
            "### [ADR-1: First task](https://jodasoft.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** ADR-2\n\n"
            "### [ADR-2: Second task](https://jodasoft.atlassian.net/browse/ADR-2) 🤖\n\n"
            "**Depends on:** ADR-1\n\n"
        )

        # Act / Assert
        with pytest.raises(TaskDependencyError) as exc_info:
            validate_stack_order(spec_text)
        assert "ADR-1" in str(exc_info.value)
        assert "ADR-2" in str(exc_info.value)

    def test_validate_stack_order_three_task_cycle_raises_error_naming_cyclic_tasks(self):
        # Arrange
        from task_dependencies import TaskDependencyError, validate_stack_order
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
            validate_stack_order(spec_text)
        assert "ADR-1" in str(exc_info.value)
        assert "ADR-2" in str(exc_info.value)
        assert "ADR-3" in str(exc_info.value)
