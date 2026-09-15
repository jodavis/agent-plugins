#!/usr/bin/env python3
"""Concurrent scheduler.

`compute_next_batch(target)` owns everything `concurrent-orchestrate`'s thin spawn loop needs
computed for it: the "up to" target's inclusive document-order task set (or the explicit list
taken as-is, with no expansion), each target task's cached status (via the Task readiness
checker), a live check for whether the epic's spec branch exists yet, and a repo-wide
concurrency cap enforced across every target's own data file — never just this one. It never
spawns anything itself.

ADR-374 changes two things from ADR-296's original scheduler: (1) the "up to" target set is now
every task from the start of the epic's document order (per the Stack order validator) through
the target inclusive — not just the target's own transitive dependency closure, since one
linear stack per epic means an earlier, unrelated task still needs implementing regardless of
whether the target depends on it; (2) `compute_next_batch` first runs a live
`git branch -r`-based check for whether `<epic-id>`'s spec branch already exists (parsed from
the spec's own `> **Epic:** [<key>](...)` header line); if not, it raises `RuntimeError` before
doing any batch computation — a task can't meaningfully start before its epic's spec does, so a
missing spec branch here means `/write-dev-spec` was never run for this epic, not something this
script (or `concurrent-orchestrate`) can remediate on its own. The live check still means a
different target against an already-bootstrapped epic proceeds straight to normal scheduling
without re-checking anything stale.

`poll_until_actionable(target)` wraps `compute_next_batch` with the blocking behavior the CLI
exposes: rather than making the calling agent re-invoke this script itself every 30 seconds
(noisy — one turn per poll), it polls internally, sleeping between cycles, and only returns once
there's something actionable to report (a non-"waiting" status, or a "waiting" status with a
non-empty `spawn`) or `--max-poll-cycles` idle cycles have elapsed with nothing to do — at which
point it returns the last "waiting"/empty result anyway, so the caller still gets a chance to
check in periodically.

Usage:
  concurrent_schedule.py --up-to <key>
  concurrent_schedule.py --list <key1,key2,...>
  concurrent_schedule.py --up-to <key> --poll-interval-seconds 30 --max-poll-cycles 10

Mirrors `compute_next_batch(target)`'s own single-argument contract: the spec file is never
passed in — it's located via `dev_team.find_spec_file()`, keyed off the target's own task id,
exactly the way `dev_team.py` itself finds a task's spec.

`main()` is a thin CLI wrapper so a prose skill (`concurrent-orchestrate`, which has no other
way to call a Python function directly) can invoke this via `Bash`: it prints
`poll_until_actionable`'s result as JSON to stdout on success, or a clear `Error: ...` message to
stderr with a non-zero exit on a dangling/cyclic spec, an invalid explicit list, or any other
failure.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_WORKFLOW_ORCHESTRATE_SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent / "workflow-orchestrate" / "scripts"
)
sys.path.insert(0, str(_WORKFLOW_ORCHESTRATE_SCRIPTS))
import dev_team  # noqa: E402 — referenced via module attribute so tests can monkeypatch dev_team.REPO_ROOT
from get_context_path import get_repo_slug  # noqa: E402
from task_dependencies import (  # noqa: E402
    HUMAN_MARKER,
    TaskDependencyError,
    parse_task_dependencies,
    parse_task_markers,
    validate_stack_order,
)
from task_readiness import (  # noqa: E402
    dependency_status,
    dependency_status_and_context,
    is_task_eligible,
    snapshot_from_status_and_context,
)

_MERGE_CONFIG_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "get-project-configuration" / "scripts" / "merge_config.py"
)

_DEFAULT_MAX_PARALLEL_TASKS = 3

_TERMINAL_STATUSES = ("done", "failed")

_DEFAULT_POLL_INTERVAL_SECONDS = 30
_DEFAULT_MAX_POLL_CYCLES = 10

# Matches the spec's own epic header line, e.g.:
#   > **Epic:** [ADR-369](https://jodasoft.atlassian.net/browse/ADR-369)
_EPIC_HEADER_RE = re.compile(r"^>\s*\*\*Epic:\*\*\s*\[([A-Z]+-\d+)\]", re.MULTILINE)


class ConcurrentScheduleError(ValueError):
    """Raised when an explicit list's upfront validation fails: some listed task's dependency
    is neither in the list nor already done."""


@dataclass(frozen=True)
class TargetSpec:
    mode: Literal["up_to", "list"]
    tasks: tuple[str, ...]  # the "up to" key as a 1-tuple, or the explicit list as given


def target_slug(target: TargetSpec) -> str:
    """Derive a `<target-slug>` that never collides between two different targets: the "up to"
    task's own key, or the sorted explicit list joined together."""
    if target.mode == "up_to":
        return f"up-to-{target.tasks[0]}"
    return "-".join(sorted(target.tasks))


def _state_dir(repo_slug: str) -> Path:
    base_env = os.environ.get("DEV_TEAM_STATE_DIR")
    base = Path(base_env) if base_env else Path.home() / ".dev-team"
    return base / repo_slug


def _data_file_path(repo_slug: str, target: TargetSpec) -> Path:
    return _state_dir(repo_slug) / f"concurrent-{target_slug(target)}.json"


def _parse_epic_id(spec_text: str) -> str | None:
    """Parse `<epic-id>` from the spec's own `> **Epic:** [<key>](...)` header line — the only
    local, MCP-free source of the epic key available to this bare script (mirroring
    `write-dev-spec`'s own step 1.5, which it can't invoke directly). Returns `None` if no such
    header line is present (a spec authored before this convention, or a malformed one) —
    callers treat that as "nothing to gate on" rather than an error."""
    match = _EPIC_HEADER_RE.search(spec_text)
    return match.group(1) if match else None


def _feature_branch_prefix(repo_root: Path) -> str:
    """Compute the literal prefix `write-dev-spec` step 1.5 derives from `git-repo.working-
    branches.task` — the same template task branches use, with `<user-alias>` substituted and
    everything from `<task-work-item-id>` onward dropped (e.g. `dev/<user-alias>/<task-work-
    item-id>-<slug>` with `user-alias: claude` becomes `dev/claude/`). There is no separate
    "feature" branch template — a feature's own spec branch is this same template with
    `<feature-work-item-id>-spec` standing in for `<task-work-item-id>` (see
    `_feature_branch_exists` below and `write-dev-spec`'s own step 1.5)."""
    result = subprocess.run(
        [sys.executable, str(_MERGE_CONFIG_SCRIPT), "--repo-root", str(repo_root)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to load project configuration: {result.stderr.strip()}")
    config = json.loads(result.stdout)
    git_repo = config.get("git-repo") or {}
    template = (git_repo.get("working-branches") or {}).get("task", "")
    user_alias = git_repo.get("user-alias") or "claude"
    template = template.replace("<user-alias>", user_alias)
    prefix, _, _ = template.partition("<task-work-item-id>")
    return prefix


def _feature_branch_exists(epic_id: str, repo_root: Path) -> bool:
    """Live check — never a data-file check — for whether `<epic-id>`'s spec branch already
    exists on the remote, mirroring the same `git branch -r` check `write-dev-spec`'s own step
    1.5 runs as its own first step. A live check avoids both looping forever (nothing ever
    writes a persisted signal) and forcing a second, different target landing on an
    already-existing epic spec branch to needlessly re-check anything stale."""
    prefix = _feature_branch_prefix(repo_root)
    result = subprocess.run(
        ["git", "branch", "-r"], cwd=repo_root, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"'git branch -r' failed: {result.stderr.strip()}")
    pattern = rf"{re.escape(prefix)}{re.escape(epic_id)}-spec(-|$)"
    return bool(re.search(pattern, result.stdout, re.MULTILINE))


def _validate_explicit_list(tasks: list[str], graph: dict[str, list[str]]) -> None:
    """Raise ConcurrentScheduleError naming the offending task and dependency if any listed
    task's dependency is neither in the list nor already done."""
    task_set = set(tasks)
    for task in tasks:
        for dep in graph.get(task, []):
            if dep in task_set:
                continue
            status = dependency_status(dep)
            if status == "done":
                continue
            raise ConcurrentScheduleError(
                f"Task {task} depends on {dep}, which is neither in the explicit list "
                f"{sorted(task_set)} nor already done (status: {status})."
            )


def _has_failed_ancestor(
    task: str, graph: dict[str, list[str]], statuses: dict[str, str], memo: dict[str, bool]
) -> bool:
    """True if any transitive dependency of `task` (per the full spec graph) has status
    "failed". Guards against a cycle by seeding `memo[task] = False` before recursing — the
    dependency graph is validated acyclic by `parse_task_dependencies` itself, so this is a
    defensive guard, not an expected path."""
    if task in memo:
        return memo[task]
    memo[task] = False
    result = False
    for dep in graph.get(task, []):
        if statuses.get(dep) == "failed" or _has_failed_ancestor(dep, graph, statuses, memo):
            result = True
            break
    memo[task] = result
    return result


def _max_parallel_tasks(repo_root: Path) -> int:
    """Return `concurrency.max-parallel-tasks` from the merged project configuration (see
    get-project-configuration skill), defaulting to 3 if unset, null, or not parseable as an
    int. `merge_config.py`'s minimal YAML parser returns every plain scalar as a string (it
    never infers numeric types), so a configured value arrives here as e.g. `"5"`, not `5`."""
    result = subprocess.run(
        [sys.executable, str(_MERGE_CONFIG_SCRIPT), "--repo-root", str(repo_root)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to load project configuration: {result.stderr.strip()}")
    config = json.loads(result.stdout)
    concurrency = config.get("concurrency") or {}
    max_parallel = concurrency.get("max-parallel-tasks")
    try:
        return int(max_parallel)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_PARALLEL_TASKS


def _repo_wide_active_spawn_count(repo_slug: str) -> int:
    """Sum still-active (non-terminal) spawns tracked across *every*
    `concurrent-<target-slug>.json` file under this repo's state directory — not just one
    target's own file, since the cap bounds compute/API load repo-wide."""
    state_dir = _state_dir(repo_slug)
    if not state_dir.is_dir():
        return 0
    count = 0
    for data_file in state_dir.glob("concurrent-*.json"):
        data = json.loads(data_file.read_text(encoding="utf-8"))
        for task_id in data.get("spawned", []):
            if dependency_status(task_id) not in _TERMINAL_STATUSES:
                count += 1
    return count


def _load_or_initialize_data(
    target: TargetSpec, data_path: Path, graph: dict[str, list[str]], order: list[str]
) -> dict:
    """Load this target's persisted data file, or build and persist it on first invocation:
    the "up to" form takes every task from the start of `order` (the epic's document order, per
    the Stack order validator) through the target inclusive — not just its dependency closure
    (ADR-296's old behavior), since one linear stack per epic means an earlier, unrelated task
    still needs implementing regardless of whether the target depends on it. The explicit list
    form is taken as-is after upfront validation, unaffected by this change."""
    if data_path.exists():
        return json.loads(data_path.read_text(encoding="utf-8"))

    if target.mode == "up_to":
        target_task = target.tasks[0]
        if target_task not in order:
            raise ConcurrentScheduleError(
                f"'up to' target {target_task!r} is not a task heading in the epic's document "
                f"order (found headings: {order}). Verify the task key is correct."
            )
        tasks = order[: order.index(target_task) + 1]
    else:
        tasks = list(target.tasks)
        _validate_explicit_list(tasks, graph)

    data = {"mode": target.mode, "tasks": tasks, "spawned": []}
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(data), encoding="utf-8")
    return data


def _running_snapshots(
    spawned: set[str], statuses_and_contexts: dict[str, tuple[str, object]]
) -> list[dict]:
    """One snapshot entry per already-spawned task that is still non-terminal, in stable
    sorted-by-task-id order — matching how every other list `compute_next_batch()` returns is
    already sorted or ordered from a sorted `tasks` list. Built from the same `(status, ctx)`
    pairs `compute_next_batch()` already read once to build `statuses` — never a second,
    independent context-file read per task — so a task's snapshot `status` can never disagree
    with the value that decided whether it's included."""
    return [
        {"task_id": task, **snapshot_from_status_and_context(*statuses_and_contexts[task])}
        for task in sorted(spawned)
        if statuses_and_contexts[task][0] not in _TERMINAL_STATUSES
    ]


def compute_next_batch(target: TargetSpec) -> dict:
    """Compute the next batch of tasks to spawn for `target`.

    Returns `{"status": "waiting" | "complete" | "blocked", "spawn": [...],
    "blocked_tasks": [...], "running": [...], "human_tasks": [...]}`. `"human_tasks"` lists any
    task that is otherwise eligible (not yet started, all dependencies satisfied) but whose
    heading is marked 🧑 (human-required, see task_dependencies.HUMAN_MARKER) — such a task is
    never included in `"spawn"`, since a human, not the Developer agent, must actually do it; it
    is reported here instead so it isn't silently dropped from view. Never spawns anything —
    deterministic computation only. Raises `RuntimeError` if the epic's spec branch doesn't exist
    yet (`/write-dev-spec` was never run for it) — there is nothing this script or its caller can
    do to remediate that on its own, so it's a hard failure rather than a retryable status.
    """
    spec_path = dev_team.find_spec_file(target.tasks[0])
    spec_text = spec_path.read_text(encoding="utf-8")
    graph = parse_task_dependencies(spec_text)
    markers = parse_task_markers(spec_text)
    # Only the "up to" form needs document order — the explicit-list form is taken as-is, no
    # expansion, so it never needs the Stack order validator's stricter ordering check.
    order = validate_stack_order(spec_text) if target.mode == "up_to" else []

    repo_slug = get_repo_slug()
    data_path = _data_file_path(repo_slug, target)
    data = _load_or_initialize_data(target, data_path, graph, order)

    epic_id = _parse_epic_id(spec_text)
    if epic_id is not None and not _feature_branch_exists(epic_id, dev_team.REPO_ROOT):
        raise RuntimeError(
            f"Epic {epic_id}'s spec branch does not exist yet. Run /write-dev-spec for "
            f"{epic_id} before starting task-level work."
        )

    tasks: list[str] = data["tasks"]
    spawned: set[str] = set(data.get("spawned", []))
    statuses_and_contexts = {task: dependency_status_and_context(task) for task in tasks}
    statuses = {task: status for task, (status, _) in statuses_and_contexts.items()}

    if all(statuses[task] == "done" for task in tasks):
        return {
            "status": "complete", "spawn": [], "blocked_tasks": [], "running": [],
            "human_tasks": [],
        }

    not_yet_started = [
        task for task in tasks if task not in spawned and statuses[task] == "not_started"
    ]
    memo: dict[str, bool] = {}
    blocked_tasks = sorted(
        task for task in not_yet_started if _has_failed_ancestor(task, graph, statuses, memo)
    )

    currently_spawned_terminal = all(statuses[task] in _TERMINAL_STATUSES for task in spawned)
    if blocked_tasks and currently_spawned_terminal:
        return {
            "status": "blocked", "spawn": [], "blocked_tasks": blocked_tasks,
            "running": _running_snapshots(spawned, statuses_and_contexts),
            "human_tasks": [],
        }

    ready: list[str] = [
        task for task in not_yet_started
        if task not in blocked_tasks and is_task_eligible(task, graph.get(task, [])) == "eligible"
    ]
    human_tasks = sorted(task for task in ready if markers.get(task) == HUMAN_MARKER)
    eligible = [task for task in ready if task not in set(human_tasks)]

    max_parallel = _max_parallel_tasks(dev_team.REPO_ROOT)
    active = _repo_wide_active_spawn_count(repo_slug)
    available = max(0, max_parallel - active)

    spawn = [{"task_id": task} for task in eligible[:available]]

    running = _running_snapshots(spawned, statuses_and_contexts)

    if spawn:
        data["spawned"] = sorted(spawned | {entry["task_id"] for entry in spawn})
        data_path.write_text(json.dumps(data), encoding="utf-8")

    return {
        "status": "waiting", "spawn": spawn, "blocked_tasks": [], "running": running,
        "human_tasks": human_tasks,
    }


def poll_until_actionable(
    target: TargetSpec,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    max_poll_cycles: int = _DEFAULT_MAX_POLL_CYCLES,
    sleep=time.sleep,
) -> dict:
    """Block until `compute_next_batch(target)` has something actionable to report, instead of
    making the caller re-invoke this script itself every 30 seconds. Polls immediately; if that
    poll comes back `"waiting"` with an empty `spawn` (nothing newly eligible and the cap isn't
    the reason — there's simply nothing to do yet), sleeps `poll_interval_seconds` and polls
    again, up to `max_poll_cycles` times. Returns as soon as any poll reports `"complete"`,
    `"blocked"`, or `"waiting"` with a non-empty `spawn` (a `RuntimeError` from
    `compute_next_batch` propagates immediately, uncaught). If every cycle
    stays idle, returns the last (still "waiting", still empty) result anyway once
    `max_poll_cycles` is exhausted, so the caller regains control periodically to sanity-check
    the run rather than blocking forever."""
    result = compute_next_batch(target)
    cycles = 0
    while result["status"] == "waiting" and not result["spawn"] and cycles < max_poll_cycles:
        sleep(poll_interval_seconds)
        result = compute_next_batch(target)
        cycles += 1
    return result


def _parse_target(args: argparse.Namespace) -> TargetSpec:
    if args.up_to:
        return TargetSpec(mode="up_to", tasks=(args.up_to,))
    tasks = tuple(task.strip() for task in args.list.split(",") if task.strip())
    return TargetSpec(mode="list", tasks=tasks)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="concurrent_schedule.py",
        description="Compute the next batch of tasks to spawn for a concurrent /implement run.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--up-to", metavar="key", help="Inclusive 'up to' target task key")
    group.add_argument("--list", metavar="key1,key2,...", help="Explicit comma-separated task list")
    parser.add_argument(
        "--poll-interval-seconds", type=float, default=_DEFAULT_POLL_INTERVAL_SECONDS,
        help="Seconds to sleep between poll cycles while 'waiting' with nothing to spawn "
             f"(default: {_DEFAULT_POLL_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--max-poll-cycles", type=int, default=_DEFAULT_MAX_POLL_CYCLES,
        help="Max number of pause-poll cycles before returning control even while still "
             f"'waiting' with nothing to spawn (default: {_DEFAULT_MAX_POLL_CYCLES}, i.e. "
             f"{_DEFAULT_MAX_POLL_CYCLES * _DEFAULT_POLL_INTERVAL_SECONDS / 60:g} minutes total)",
    )
    args = parser.parse_args()

    target = _parse_target(args)

    try:
        result = poll_until_actionable(
            target,
            poll_interval_seconds=args.poll_interval_seconds,
            max_poll_cycles=args.max_poll_cycles,
        )
    except (
        TaskDependencyError,
        ConcurrentScheduleError,
        OSError,
        RuntimeError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
