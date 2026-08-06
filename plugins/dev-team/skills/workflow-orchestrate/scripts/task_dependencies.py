#!/usr/bin/env python3
"""Parse a spec's `## Tasks` section into a task dependency graph.

Usage: task_dependencies.py <path to spec file>

`spec-task-breakdown` step 5 rewrites every task's title into a `[KEY: Title](url)`-style
hyperlink and every `**Depends on:**` local task-number reference into the real task-work-item
key assigned to that task. Once that rewrite is complete, `parse_task_dependencies` is the
single validation pass over the whole `## Tasks` section — it is never called before the
rewrite and never needs to understand the local-numbering form.

`main()` is a thin CLI wrapper so a prose skill (`spec-task-breakdown`, which has no other way
to call a Python function directly) can invoke this via `Bash`: it prints the resulting graph as
JSON to stdout on success, or a clear `Error: ...` message to stderr with a non-zero exit on a
dangling reference, a dependency cycle, or a missing/unreadable spec file.
"""

import json
import re
import sys
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

# Matches an already-rewritten task heading, e.g.:
#   ### [ADR-307: Dependency declaration and graph parsing](https://jodasoft.atlassian.net/browse/ADR-307) 🤖
TASK_HEADING_RE = re.compile(
    r"^### \[([A-Z]+-\d+):[^\]]*\]\([^)]*\)\s*(?:🤖|🧑)\s*$",
    re.MULTILINE,
)

# Matches the field line directly: '**Depends on:** ADR-1, ADR-2' or '**Depends on:** — none —'
DEPENDS_ON_RE = re.compile(r"^\*\*Depends on:\*\*\s*(.+?)\s*$", re.MULTILINE)

# The literal '— none —' placeholder (em dashes), tolerant of surrounding whitespace.
NONE_RE = re.compile(r"^—\s*none\s*—$")


class TaskDependencyError(ValueError):
    """Raised when a spec's `Depends on:` entries form an invalid dependency graph.

    Covers both a dangling reference (a `Depends on:` entry naming a task not present in the
    spec) and a dependency cycle. The message always names the offending task and reference
    (dangling case) or the cyclic task keys (cycle case).
    """


def parse_task_dependencies(spec_text: str) -> dict[str, list[str]]:
    """Parse a spec's rewritten `## Tasks` section into a dependency graph.

    Maps each real task-work-item key to its list of dependency task-keys. A task with no
    `Depends on:` line, or an explicit `**Depends on:** — none —` line, maps to an empty list.

    Raises TaskDependencyError, naming the offending task and reference, if any `Depends on:`
    entry names a task not present in this spec (dangling reference), or if the resulting
    dependency graph contains a cycle.
    """
    headings = list(TASK_HEADING_RE.finditer(spec_text))
    known_keys = {match.group(1) for match in headings}

    graph: dict[str, list[str]] = {}
    for index, match in enumerate(headings):
        task_key = match.group(1)
        section_end = headings[index + 1].start() if index + 1 < len(headings) else len(spec_text)
        section_text = spec_text[match.end():section_end]

        depends_match = DEPENDS_ON_RE.search(section_text)
        if depends_match is None:
            graph[task_key] = []
            continue

        raw_value = depends_match.group(1).strip()
        if NONE_RE.match(raw_value):
            graph[task_key] = []
            continue

        dependencies = [ref.strip() for ref in raw_value.split(",")]
        for ref in dependencies:
            if ref not in known_keys:
                raise TaskDependencyError(
                    f"Task {task_key} declares a dependency on '{ref}', but no task with that "
                    f"key exists in this spec."
                )
        graph[task_key] = dependencies

    try:
        TopologicalSorter(graph).prepare()
    except CycleError as e:
        cycle = e.args[1]
        raise TaskDependencyError(
            f"Dependency cycle detected among tasks: {' -> '.join(cycle)}"
        ) from e

    return graph


def validate_stack_order(spec_text: str) -> list[str]:
    """Extend parse_task_dependencies with a stack-order check.

    Confirms that every task's `Depends on:` entries appear earlier in the spec's document
    order than the task itself, then returns the task keys in that same document order.

    Raises TaskDependencyError for the same dangling-reference/cycle cases as
    parse_task_dependencies, plus when a task is listed before one of its own dependencies.
    """
    graph = parse_task_dependencies(spec_text)
    order = list(graph.keys())
    position = {task_key: index for index, task_key in enumerate(order)}

    for task_key, dependencies in graph.items():
        for dependency_key in dependencies:
            if position[dependency_key] > position[task_key]:
                raise TaskDependencyError(
                    f"Task {task_key} is listed before its dependency {dependency_key}; "
                    f"tasks must appear after every task they depend on."
                )

    return order


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {Path(sys.argv[0]).name} <path to spec file>", file=sys.stderr)
        sys.exit(1)

    spec_path = Path(sys.argv[1])
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"Error: could not read spec file '{spec_path}': {e}", file=sys.stderr)
        sys.exit(1)

    try:
        graph = parse_task_dependencies(spec_text)
    except TaskDependencyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(graph), flush=True)


if __name__ == "__main__":
    main()
