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
dangling reference, a dependency cycle, a heading missing/malformed on its trailing 🤖/🧑
marker (see `validate_task_headings`), or a missing/unreadable spec file.
"""

import json
import re
import sys
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

# The two markers a task heading must end in: 🤖 for an agent task, 🧑 for a human-required one
# (configuration, infrastructure setup, access provisioning — see dev-spec-task-breakdown).
AGENT_MARKER = "🤖"
HUMAN_MARKER = "🧑"

# Matches an already-rewritten task heading, e.g.:
#   ### [ADR-307: Dependency declaration and graph parsing](https://jodasoft.atlassian.net/browse/ADR-307) 🤖
TASK_HEADING_RE = re.compile(
    rf"^### \[([A-Z]+-\d+):[^\]]*\]\([^)]*\)\s*({AGENT_MARKER}|{HUMAN_MARKER})\s*$",
    re.MULTILINE,
)

# A looser pattern that matches any line that looks like it was meant to be a task heading —
# the `### [KEY: Title](url)` prefix — regardless of what (if anything) follows it. Used only by
# validate_task_headings to positively detect a heading that fails to fully match
# TASK_HEADING_RE (e.g. a missing or malformed trailing marker) instead of that heading simply
# vanishing from parse_task_dependencies'/parse_task_markers' output with no error at all.
_CANDIDATE_HEADING_RE = re.compile(
    r"^### \[([A-Z]+-\d+):[^\]]*\]\([^)]*\).*$",
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


def parse_task_markers(spec_text: str) -> dict[str, str]:
    """Parse a spec's rewritten `## Tasks` section into a mapping of each task's key to the
    human/agent marker (HUMAN_MARKER or AGENT_MARKER) its heading was labeled with.

    A heading that doesn't fully match TASK_HEADING_RE (e.g. missing or malformed marker) is
    silently absent from the returned mapping, exactly like parse_task_dependencies silently
    excludes it from its own graph — this function never raises. Use validate_task_headings for
    the stricter, opt-in check that raises TaskDependencyError naming such a heading.
    """
    return {match.group(1): match.group(2) for match in TASK_HEADING_RE.finditer(spec_text)}


def validate_task_headings(spec_text: str) -> None:
    """Raise TaskDependencyError, naming the offending heading, if any line in the spec looks
    like it was meant to be a task heading (the `### [KEY: Title](url)` prefix) but doesn't
    fully match the required `### [KEY: Title](url) 🤖`/`🧑` format — most commonly a missing or
    malformed trailing human/agent marker.

    This is a stricter, opt-in check distinct from parse_task_dependencies/parse_task_markers,
    which both silently exclude any non-matching heading from their own output rather than
    raising. Keeping that leniency in the two parsing functions preserves today's behavior for
    every already-existing spec read at scheduling time (e.g. by compute_next_batch); this
    function is meant to be invoked once, right when a task's heading is finalized (e.g.
    dev-spec-create-work-items step 3, immediately after rewriting a task's title into a
    hyperlink), which is the appropriate point to catch a missing/malformed marker close to its
    source rather than downstream.
    """
    for match in _CANDIDATE_HEADING_RE.finditer(spec_text):
        heading_line = spec_text[match.start():match.end()]
        if TASK_HEADING_RE.match(heading_line) is None:
            raise TaskDependencyError(
                f"Task {match.group(1)}'s heading is missing or has a malformed trailing "
                f"🤖/🧑 marker: {heading_line.strip()!r}"
            )


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
        validate_task_headings(spec_text)
        graph = parse_task_dependencies(spec_text)
    except TaskDependencyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(graph), flush=True)


if __name__ == "__main__":
    main()
