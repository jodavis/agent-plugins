#!/usr/bin/env python3
"""dev-team pipeline engine — generic state-machine infrastructure shared by every pipeline.

This module contains no pipeline-specific `Step` subclasses or state maps. Concrete
pipelines live in their own leaf scripts (`implement.py` for the implement/fix task
pipeline, `monitor_prs.py` for the long-lived PR monitor), each of which builds its own
`step_handlers` dict and calls `run_pipeline()` below.

To start a pipeline fresh, delete its context file:
  ~/.dev-team/<repo-slug>/<work-item-id>.md
"""

import json
import os
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, NoReturn

from pipeline_context import PipelineContext

# Reconfigure stdout/stderr to UTF-8 early so that Unicode characters in agent
# output (e.g. arrows, bullets) don't crash on Windows cp1252 terminals.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# The only threshold generic enough to live in the engine — every Step, in any pipeline,
# can increment/reset ctx.consecutive_failures via _handle_agent_failure/_handle_agent_success.
# Pipeline-specific thresholds (e.g. implement.py's signoff/review-loop bounds) are supplied by
# the calling leaf script as `troubleshooter_checks` to run_pipeline()/DevTeamPipeline.
CONSECUTIVE_FAILURES_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Step-machine exit protocol
# ---------------------------------------------------------------------------

def exit_with_actions(descriptors: list[dict]) -> NoReturn:
    """Emit a JSON array of action descriptors on stdout and exit 0.

    Called when the pipeline needs one or more agents/scripts to run. The
    orchestration loop (workflow-orchestrate) parses this array, dispatches each item
    in parallel, then re-invokes the script.
    """
    print(json.dumps(descriptors), flush=True)
    sys.exit(0)


def compute_context_path(work_item_id: str, repo_slug: str) -> Path:
    """Compute the context file path for a work item.

    Base: DEV_TEAM_STATE_DIR env var, or ~/.dev-team if unset.
    Full path: <base>/<repo_slug>/<work_item_id>.md

    This helper is used by get_context_path.py before invoking a pipeline script. The
    scripts themselves receive --context-file as a required argument with no fallback.
    """
    base_env = os.environ.get("DEV_TEAM_STATE_DIR")
    base = Path(base_env) if base_env else Path.home() / ".dev-team"
    return base / repo_slug / f"{work_item_id}.md"


# ---------------------------------------------------------------------------
# Pending scratch-file deliverables (see issue #191)
# ---------------------------------------------------------------------------
#
# Nested skills invoked via `workflow-worker` used to be asked to both produce a large
# deliverable as their final chat message *and* remember to write it to the shared context file
# afterward, in the same turn. That reliably failed: producing the deliverable is the model's
# natural stopping point, and no "keep going after this" instruction survived reaching it. Skills
# now compose their deliverable directly as the content of a `Write` call to a private scratch
# file instead — never printed as chat text, so there is no separate "also remember to..." step to
# skip — then return a single word (`successful`) as their entire final message. This
# preprocessing step is the deterministic (non-LLM) counterpart that actually lands that content
# in the shared context file. Callers must invoke this themselves for any context file they
# expect an agent to have written a scratch deliverable against — run_pipeline() does this
# automatically for the pipeline's own work item, but a Step whose spawned agent targets a
# *different* work item's context file (e.g. monitor_prs.py's ReactStep/ResolvingConflictStep,
# which dispatch against a task's own file, not the monitor's) must call this explicitly itself.

_PENDING_DIR_NAME = ".pending"
_SECTION_SENTINEL_PREFIX = "<!-- section:"
_SECTION_SENTINEL_SUFFIX = " -->"


def _replace_or_append_section(context_text: str, section_name: str, content: str) -> str:
    """Deterministic counterpart to the Edit-based sentinel-replace-or-append convention
    `workflow-worker`/`use-context-file` describe for agent-driven writes: replace everything
    between `<!-- section:<section_name> -->` and the next `<!-- section:` marker (or end of
    file), or append a new sentinel + content if it doesn't already exist."""
    sentinel = f"{_SECTION_SENTINEL_PREFIX}{section_name}{_SECTION_SENTINEL_SUFFIX}"
    lines = context_text.splitlines()
    new_block = [sentinel, "", content.strip(), ""]

    start = next((i for i, line in enumerate(lines) if line.strip() == sentinel), None)
    if start is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.extend(new_block)
        return "\n".join(lines) + "\n"

    end = len(lines)
    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith(_SECTION_SENTINEL_PREFIX) and stripped.endswith(_SECTION_SENTINEL_SUFFIX):
            end = j
            break
    lines[start:end] = new_block
    return "\n".join(lines) + "\n"


def merge_pending_deliverables(context_path: Path, work_item_id: str) -> None:
    """Merge every pending `<work-item-id>__<section-name>.md` scratch file in the context
    file's sibling `.pending/` directory into the context file itself, then delete each one.

    `<section-name>` is the scratch filename's stem after the `<work-item-id>__` prefix, with
    underscores standing in for the spaces in the real section name (no shipped section name
    contains a literal underscore, so this mapping is unambiguous to reverse). A no-op — cheap
    and safe to call unconditionally — when the `.pending/` directory doesn't exist or holds
    nothing for this work item."""
    pending_dir = context_path.parent / _PENDING_DIR_NAME
    if not pending_dir.is_dir():
        return

    prefix = f"{work_item_id}__"
    scratch_paths = sorted(p for p in pending_dir.glob(f"{prefix}*.md") if p.is_file())
    if not scratch_paths:
        return

    context_text = context_path.read_text(encoding="utf-8") if context_path.exists() else ""
    for scratch_path in scratch_paths:
        section_name = scratch_path.stem[len(prefix):].replace("_", " ")
        content = scratch_path.read_text(encoding="utf-8")
        context_text = _replace_or_append_section(context_text, section_name, content)
    context_path.write_text(context_text, encoding="utf-8")

    for scratch_path in scratch_paths:
        scratch_path.unlink()


# ---------------------------------------------------------------------------
# Workflow definition (parsed from a Mermaid stateDiagram-v2 file)
# ---------------------------------------------------------------------------

@dataclass
class WorkflowDefinition:
    transitions: dict[str, dict[str, str]]
    terminal_states: set[str]
    initial_state: str


def parse_workflow(path: Path) -> WorkflowDefinition:
    """Parse a Mermaid stateDiagram-v2 block from a markdown file.

    Recognises three line forms inside the diagram:
      [*] --> StateA          → initial state
      StateA --> [*]          → terminal state
      StateA --> StateB : t   → transition with trigger t (src == dst is allowed — a
                                 self-transition, used by long-lived polling states)
    """
    text = path.read_text(encoding="utf-8")

    match = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
    if not match:
        raise ValueError(f"No mermaid fenced block found in {path}")

    transitions: dict[str, dict[str, str]] = {}
    terminal_states: set[str] = set()
    initial_state: str | None = None

    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if "-->" not in line:
            continue

        m = re.match(r"^([\w-]+)\s+-->\s+\[\*\]$", line)
        if m:
            terminal_states.add(m.group(1))
            continue

        m = re.match(r"^\[\*\]\s+-->\s+([\w-]+)$", line)
        if m:
            initial_state = m.group(1)
            continue

        m = re.match(r"^([\w-]+)\s+-->\s+([\w-]+)\s*:\s*([\w-]+)$", line)
        if m:
            src, dst, trigger = m.group(1), m.group(2), m.group(3)
            transitions.setdefault(src, {})[trigger] = dst
            continue

    if initial_state is None:
        raise ValueError(f"No initial state ([*] --> ...) found in {path}")

    return WorkflowDefinition(
        transitions=transitions,
        terminal_states=terminal_states,
        initial_state=initial_state,
    )


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class StateMachine:
    """Simple state machine backed by a dict-of-dicts transition table."""

    def __init__(self, transitions: dict[str, dict[str, str]], initial: str) -> None:
        self._transitions = transitions
        self.state = initial

    def transition(self, trigger: str) -> str:
        """Advance to the next state via trigger. Returns new state."""
        available = self._transitions.get(self.state, {})
        if trigger not in available:
            raise ValueError(
                f"Invalid trigger '{trigger}' from state '{self.state}'. "
                f"Available: {list(available)}"
            )
        self.state = available[trigger]
        return self.state


def _parse_sections(body: str) -> dict[str, str]:
    """Split a markdown body into {heading: content} by '<!-- section:Name -->' sentinels."""
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in body.split("\n"):
        if line.startswith("<!-- section:") and line.endswith(" -->"):
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = line[len("<!-- section:"):-len(" -->")].strip()
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body. Returns (metadata_dict, body). Generic utility for a
    Step that needs to re-read a raw context file's sections directly (e.g. as a fallback when
    a structured field wasn't populated, or when reading a *different* work item's context
    file than the one this pipeline is driving)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text

    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break

    if end is None:
        return {}, text

    frontmatter_lines = lines[1:end]
    body = "\n".join(lines[end + 1:]).lstrip("\n")

    metadata: dict = {}
    i = 0
    while i < len(frontmatter_lines):
        line = frontmatter_lines[i]
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if not value:
                items: list[str] = []
                j = i + 1
                while j < len(frontmatter_lines):
                    item_line = frontmatter_lines[j].strip()
                    if item_line.startswith("- "):
                        items.append(item_line[2:].strip())
                        j += 1
                    else:
                        break
                if items:
                    metadata[key] = items
                    i = j
                    continue
            metadata[key] = value
        i += 1

    return metadata, body


# ---------------------------------------------------------------------------
# Project configuration / hook resolution
# ---------------------------------------------------------------------------

_MERGE_CONFIG_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "get-project-configuration" / "scripts" / "merge_config.py"
)


def _load_project_config(repo_root: Path) -> dict:
    """Return the merged project configuration (see get-project-configuration skill)."""
    result = subprocess.run(
        [sys.executable, str(_MERGE_CONFIG_SCRIPT), "--repo-root", str(repo_root)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to load project configuration: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _project_configuration(ctx: "PipelineContext") -> dict:
    """Return the project configuration cached on `ctx.project_configuration` at
    context-file creation time, or {} if it was never populated."""
    if not ctx.project_configuration:
        return {}
    return json.loads(ctx.project_configuration)


def _resolve_hook_map(config: dict, key: str) -> dict:
    """Return the ordered label:instruction map configured under one `instructions:` key.

    Filters out any entry disabled via a null/"" value (the existing per-label disable
    convention — a more specific config tier can silence one inherited label without
    touching its siblings). An absent or entirely null/empty key resolves to {}.

    The label is only meaningful here and in the merge step that follows (deduplicating an
    entry a trigger-specific and an unconditional key both define) — once merged, only the
    surviving instruction *text* is ever handed to a "hooks" action descriptor, as a bare list.
    """
    instructions = config.get("instructions") or {}
    entries = instructions.get(key) or {}
    return {label: instruction for label, instruction in entries.items() if instruction}


def parse_json_output(text: str) -> dict:
    """Extract the last parseable JSON object from agent output text."""
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    for block in reversed(re.findall(r"```(?:json)?\s*\n([\s\S]*?)\n```", text)):
        try:
            result = json.loads(block.strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            continue

    return {}


def _troubleshooter_descriptor(
    trigger: str, context_path: Path, ctx: "PipelineContext", count: int
) -> dict:
    """Build the exit descriptor for a troubleshooter spawn."""
    return {
        "action": "spawn_agent",
        "message": f"Pipeline issue detected (trigger: {trigger}). Troubleshooter is intervening.",
        "skill": "troubleshooter",
        "trigger": trigger,
        "context_file": str(context_path),
        "cycle_count": count,
    }


def _check_and_trigger_troubleshooter(
    trigger: str,
    threshold: int,
    count: int,
    ctx: "PipelineContext",
    context_path: Path,
) -> None:
    """Exit with a troubleshooter descriptor if count has reached threshold."""
    if count >= threshold:
        ctx.save(context_path)
        exit_with_actions([_troubleshooter_descriptor(trigger, context_path, ctx, count)])


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

class Step(ABC):
    """A single phase of a dev-team pipeline."""

    handles: str

    # Stable event name _do_get_actions_and_exit() uses to resolve before-<event>/
    # after-<event>-<trigger> instructions from the project's `instructions:` config and
    # dispatch them as their own "hooks" pipeline steps. None means this Step has no single
    # wrappable agent/script session (e.g. an inline step, or a ParallelSteps composite with
    # no single action of its own) and no hooks apply to it.
    EVENT_NAME: str | None = None

    @abstractmethod
    def get_actions(self) -> list[dict]:
        """Return action descriptors to dispatch. Empty list means inline step."""
        ...

    @abstractmethod
    def handle_results(self) -> str:
        """Process results from the context file and return a trigger moniker."""
        ...


def _handle_agent_failure(ctx: "PipelineContext") -> None:
    """Increment consecutive_failures after an agent/script return was empty or unparseable."""
    ctx.consecutive_failures += 1


def _handle_agent_success(ctx: "PipelineContext") -> None:
    """Reset consecutive_failures after any successful agent/script return."""
    ctx.consecutive_failures = 0


class ParallelSteps(Step):
    """Composite step that dispatches multiple child steps in parallel.

    get_actions() concatenates all children's actions into a single flat list.
    handle_results() calls each child's handle_results() and passes the resulting
    monikers to combine_results() — a subclass hook, since which trigger names take
    precedence over which is pipeline-specific (e.g. implement.py's SignoffStep uses
    "failed" > "changes_requested" > "approved").
    """

    def __init__(self, steps: list["Step"]) -> None:
        self._steps = steps

    def get_actions(self) -> list[dict]:
        all_actions: list[dict] = []
        for step in self._steps:
            actions = step.get_actions()
            all_actions.extend(actions)
        return all_actions

    def handle_results(self) -> str:
        child_monikers: list[str] = []
        for step in self._steps:
            moniker = step.handle_results()
            child_monikers.append(moniker)
        return self.combine_results(child_monikers)

    @abstractmethod
    def combine_results(self, child_monikers: list[str]) -> str:
        """Combine child monikers into a single trigger for the state machine."""
        ...


def _step_pending_key(step: Step) -> str:
    """Return the pending_agent key for a step, falling back to handles."""
    if hasattr(step, "_PENDING_KEY"):
        return step._PENDING_KEY  # type: ignore[attr-defined]
    if hasattr(step, "handles"):
        return step.handles
    return ""


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class DevTeamPipeline:
    """Drives a pipeline's state machine from init (or a resumed state) to done.

    `step_handlers` and the optional `counter_updater`/`troubleshooter_checks` callbacks are
    supplied by the calling leaf script — this class has no knowledge of any specific
    pipeline's states, fields, or thresholds.
    """

    def __init__(
        self,
        ctx: PipelineContext,
        context_path: Path,
        workflow: WorkflowDefinition,
        step_handlers: dict[str, Step],
        counter_updater: Callable[[PipelineContext, str, str], None] | None = None,
        troubleshooter_checks: list[tuple[str, int, str]] | None = None,
    ) -> None:
        self.ctx = ctx
        self.context_path = context_path
        self.workflow = workflow
        self.machine = StateMachine(workflow.transitions, initial=ctx.state)
        self.step_handlers = step_handlers
        self._counter_updater = counter_updater
        self._troubleshooter_checks = troubleshooter_checks or []

    def _dispatch_step(self, step: Step) -> str:
        """Dispatch a step: get actions, exit if non-empty, else return trigger inline."""
        return self._do_get_actions_and_exit(step)

    def _do_get_actions_and_exit(self, step: Step) -> str:
        """Gate a step's dispatch through before-hook / main action / after-hook phases.

        For a step with no EVENT_NAME, this is exactly get_actions()-then-handle_results(),
        unchanged. For a step with EVENT_NAME set, before returning a trigger to run() it also
        resolves and dispatches this project's configured before-<event>/after-<event>-<trigger>
        instructions (if any) as their own "hooks" action — a step this function may be
        re-entered for multiple times, tracked via ctx.hook_phase, before the real trigger is
        ever returned. The orchestration loop is synchronous (dispatch an action, await its
        result, re-invoke this script), so by the time this function sees hook_phase == "before"
        or "after" again, that hook dispatch has already finished — nothing about its outcome is
        inspected here; a failed hook surfaces through the orchestrator's own per-item result
        logging, the same as any other failed dispatch item.

        ctx.hook_phase == "" is reserved for "before-hooks haven't been resolved for this step
        yet" — the one signal the top-of-function check uses to decide whether to dispatch them.
        Once a before-hook has actually been dispatched and completes, this must NOT go back to
        "" — the main action's own get_actions()/handle_results() cycle can legitimately take
        several more re-entries of this function to resolve (e.g. a spawned agent needing a
        retry), and resetting to "" here would make the very next re-entry misread "" as "fresh
        step, haven't dispatched before-hooks yet" and re-dispatch them a second time before the
        main action ever gets a chance to complete. Instead it moves to the intermediate "main"
        phase, which the after-hook check below also treats as "ready" (alongside "" itself, for
        steps whose before-hooks were never configured), so a step whose main action takes
        multiple re-entries to resolve never re-fires either hook.
        """
        ctx = self.ctx
        event_name = getattr(step, "EVENT_NAME", None)
        config = _project_configuration(ctx) if event_name else None

        if event_name:
            if ctx.hook_phase == "":
                before = _resolve_hook_map(config, f"before-{event_name}")
                if before:
                    ctx.hook_phase = "before"
                    ctx.save(self.context_path)
                    exit_with_actions([{
                        "action": "hooks",
                        "message": f"Running before-{event_name} instructions.",
                        "instructions": list(before.values()),
                        "context_file": str(self.context_path),
                    }])
            elif ctx.hook_phase == "before":
                ctx.hook_phase = "main"
                ctx.save(self.context_path)

        if not ctx.pending_trigger:
            # Only call get_actions() while the trigger hasn't been computed yet. Once
            # pending_trigger is set, handle_results() already consumed the step's own
            # "is my data here yet" signal (e.g. ctx.validate_result) — calling get_actions()
            # again during an after-hook resumption would misread that consumed signal as
            # "no result yet" and re-dispatch the main action a second time.
            actions = step.get_actions()
            if actions:
                self.ctx.pending_agent = _step_pending_key(step)
                self.ctx.save(self.context_path)
                exit_with_actions(actions)

        if not event_name:
            # Inline step, no hooks apply.
            return step.handle_results()

        if ctx.pending_trigger:
            trigger = ctx.pending_trigger
        else:
            trigger = step.handle_results()
            ctx.pending_trigger = trigger
            ctx.save(self.context_path)

        if ctx.hook_phase in ("", "main"):
            after = _resolve_hook_map(config, f"after-{event_name}-{trigger}")
            after_unconditional = _resolve_hook_map(config, f"after-{event_name}")
            merged = {**after, **after_unconditional}
            if merged:
                ctx.hook_phase = "after"
                ctx.save(self.context_path)
                exit_with_actions([{
                    "action": "hooks",
                    "message": f"Running after-{event_name} instructions.",
                    "instructions": list(merged.values()),
                    "context_file": str(self.context_path),
                }])
            elif ctx.hook_phase == "main":
                # No after-hooks configured: clear the "main" marker now, rather than let it
                # leak into the next step (a different EVENT_NAME) and be mistaken there for
                # "before-hooks already handled" when they never were for that step.
                ctx.hook_phase = ""
                ctx.save(self.context_path)
        elif ctx.hook_phase == "after":
            ctx.hook_phase = ""
            ctx.save(self.context_path)

        ctx.pending_trigger = ""
        return trigger

    def run(self) -> None:
        if self.machine.state == self.workflow.initial_state:
            boot_trigger = next(iter(self.workflow.transitions[self.workflow.initial_state]))
            self.machine.transition(boot_trigger)
            self.ctx.state = self.machine.state
            self.ctx.save(self.context_path)

        while self.machine.state not in self.workflow.terminal_states:
            step = self.step_handlers.get(self.machine.state)
            if step is None:
                # Unknown state — trigger troubleshooter
                self.ctx.save(self.context_path)
                exit_with_actions([{
                    "action": "spawn_agent",
                    "message": "Pipeline entered an unknown state. Troubleshooter is intervening.",
                    "skill": "troubleshooter",
                    "trigger": "unknown_state",
                    "context_file": str(self.context_path),
                    "cycle_count": 0,
                }])

            current_state = self.machine.state
            trigger = self._dispatch_step(step)

            if self._counter_updater is not None:
                self._counter_updater(self.ctx, current_state, trigger)

            # Check pipeline-specific troubleshooter-escalation thresholds, if any were supplied.
            for field_name, threshold, trigger_label in self._troubleshooter_checks:
                count = getattr(self.ctx, field_name)
                if count >= threshold:
                    self.ctx.save(self.context_path)
                    exit_with_actions([_troubleshooter_descriptor(
                        trigger_label, self.context_path, self.ctx, count
                    )])

            self.machine.transition(trigger)
            self.ctx.state = self.machine.state
            self.ctx.save(self.context_path)

        if self.machine.state == "done":
            exit_with_actions([{
                "action": "done",
                "result": "success",
                "reason": f"Pipeline completed for {self.ctx.work_item_id}",
            }])
        else:
            exit_with_actions([{
                "action": "done",
                "result": "failed",
                "reason": f"Pipeline ended in state '{self.machine.state}' for {self.ctx.work_item_id}",
            }])


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """Walk up from cwd until a directory containing .claude/ or a .git file or directory is found."""
    current = Path(os.getcwd()).resolve()
    while True:
        if (current / ".claude").is_dir() or (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            raise RuntimeError(
                f"Could not locate repo root: no .claude/ or .git file or directory found "
                f"in any ancestor of {Path(os.getcwd()).resolve()}"
            )
        current = parent


REPO_ROOT = _find_repo_root()


# ---------------------------------------------------------------------------
# Entry point helper
# ---------------------------------------------------------------------------

def run_pipeline(
    work_item_id: str,
    workflow_path: Path,
    context_path: Path,
    step_handlers_factory: Callable[[PipelineContext, Path], dict[str, Step]],
    counter_updater: Callable[[PipelineContext, str, str], None] | None = None,
    troubleshooter_checks: list[tuple[str, int, str]] | None = None,
) -> NoReturn:
    """Load/create the context file, merge pending deliverables, build this pipeline's
    step_handlers (via the factory, since Step constructors need the now-loaded ctx/context
    path), and run the pipeline to its next agent/script dispatch or terminal state.

    Never returns — always calls exit_with_actions() (sys.exit(0)) or sys.exit(1) on a
    workflow-loading error, matching every pipeline script's previous behavior as a
    standalone `main()`.
    """
    try:
        workflow = parse_workflow(workflow_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading workflow: {e}", file=sys.stderr)
        sys.exit(1)

    merge_pending_deliverables(context_path, work_item_id)

    if context_path.exists():
        ctx = PipelineContext.load(context_path)
        if ctx.state in workflow.terminal_states:
            print(f"Previous run ended with state '{ctx.state}'.")
            print(f"Delete {context_path} to run again.")
            exit_with_actions([{
                "action": "done",
                "result": "success" if ctx.state == "done" else "failed",
                "reason": f"Pipeline previously ended in state '{ctx.state}'",
            }])
        print(f"Resuming {work_item_id} from state '{ctx.state}'...", flush=True)
    else:
        ctx = PipelineContext(work_item_id=work_item_id, state=workflow.initial_state)
        ctx.project_configuration = json.dumps(_load_project_config(REPO_ROOT), indent=2)
        ctx.save(context_path)

    step_handlers = step_handlers_factory(ctx, context_path)
    DevTeamPipeline(
        ctx, context_path, workflow, step_handlers, counter_updater, troubleshooter_checks,
    ).run()
