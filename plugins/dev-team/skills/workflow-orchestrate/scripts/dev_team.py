#!/usr/bin/env python3
"""dev-team pipeline step machine.

Entry point: main() — accepts a Jira work item ID and context file path, runs the
dev-team pipeline until an agent is needed, then exits with a JSON descriptor on
stdout (exit code 0). The orchestration loop in dev-team.md re-invokes this script
after each agent run.

To start fresh, delete the context file:
  ~/.dev-team/<repo-slug>/<work-item-id>.md
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from pipeline_context import PipelineContext

# Reconfigure stdout/stderr to UTF-8 early so that Unicode characters in agent
# output (e.g. arrows, bullets) don't crash on Windows cp1252 terminals.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

MAX_FIX_ITERATIONS = 5
MAX_REVIEW_FIX_ITERATIONS = 3
CONSECUTIVE_FAILURES_THRESHOLD = 3
SIGNOFF_DEADLOCK_THRESHOLD = 2
REVIEW_LOOP_THRESHOLD = MAX_REVIEW_FIX_ITERATIONS


# ---------------------------------------------------------------------------
# Step-machine exit protocol
# ---------------------------------------------------------------------------

def exit_with_actions(descriptors: list[dict]) -> NoReturn:
    """Emit a JSON array of action descriptors on stdout and exit 0.

    Called when the pipeline needs one or more agents/scripts to run. The
    orchestration loop in dev-team.md parses this array, dispatches each item
    in parallel, then re-invokes the script.
    """
    print(json.dumps(descriptors), flush=True)
    sys.exit(0)


def compute_context_path(work_item_id: str, repo_slug: str) -> Path:
    """Compute the context file path for a work item.

    Base: DEV_TEAM_STATE_DIR env var, or ~/.dev-team if unset.
    Full path: <base>/<repo_slug>/<work_item_id>.md

    This helper is used by dev-team.md before invoking the script. The script
    itself receives --context-file as a required argument with no fallback.
    """
    base_env = os.environ.get("DEV_TEAM_STATE_DIR")
    base = Path(base_env) if base_env else Path.home() / ".dev-team"
    return base / repo_slug / f"{work_item_id}.md"


# ---------------------------------------------------------------------------
# Counter helpers
# ---------------------------------------------------------------------------

def _apply_counter_updates(ctx: "PipelineContext", step_name: str, trigger: str) -> None:
    """Update pipeline counters after a step returns a trigger.

    Called by DevTeamPipeline.run() after a step returns normally (not via
    exit_with_actions). The step_name is the state that just completed.
    """
    if step_name == "reviewing":
        ctx.review_cycle_count += 1
    elif step_name == "signoff":
        if trigger == "changes_requested":
            ctx.signoff_cycle_count += 1
        elif trigger == "approved":
            ctx.signoff_cycle_count = 0
            ctx.review_cycle_count = 0


def _handle_agent_failure(ctx: "PipelineContext") -> None:
    """Increment consecutive_failures after an agent return was empty or unparseable."""
    ctx.consecutive_failures += 1


def _handle_agent_success(ctx: "PipelineContext") -> None:
    """Reset consecutive_failures after any successful agent return."""
    ctx.consecutive_failures = 0


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
      StateA --> StateB : t   → transition with trigger t
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_failing_pr_checks(pr_url: str) -> str:
    """Run `gh pr checks <pr_url>` and return output for failing checks.

    Returns a string with failing check lines, or empty string if all pass or
    if gh is unavailable / the command fails.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "checks", pr_url],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        # Return lines that indicate a failing check (non-passing status)
        failing_lines = [
            line for line in output.splitlines()
            if any(word in line.lower() for word in ("fail", "error", "x "))
        ]
        return "\n".join(failing_lines) if failing_lines else ""
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return ""


def _commit_and_push(work_item_id: str) -> None:
    """Push the current branch. The developer is expected to have already committed."""
    try:
        subprocess.run(["git", "add", "-A"], check=True, cwd=REPO_ROOT, capture_output=True)
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT, capture_output=True,
        )
        if diff.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", f"{work_item_id}: uncommitted changes at validation"],
                check=True, cwd=REPO_ROOT, capture_output=True,
            )
        subprocess.run(
            ["git", "push", "origin", "HEAD"],
            check=True, cwd=REPO_ROOT, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Warning: git commit/push failed (continuing): {e.stderr}", flush=True)


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
    context-file creation time."""
    return json.loads(ctx.project_configuration)


def _resolve_validation_script(config: dict, repo_root: Path) -> str | None:
    """Return the command line that runs this project's validation commands, or None if
    unconfigured.

    `validation` is a list of shell command strings, run in order from the repo root by
    run_validation.py. A project without any validation commands (e.g. a repo the user
    doesn't own) opts out by leaving `validation` null, absent, or an empty list in its
    .dev-team/config.yaml — see get-project-configuration's null-value convention.
    """
    validation = config.get("validation")
    if not validation:
        return None
    run_validation_script = Path(__file__).parent / "run_validation.py"
    return f'{sys.executable} "{run_validation_script}" --repo-root "{repo_root}"'


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


def _researcher_validated(content: str) -> bool:
    """Return True if researcher-validate reported success.

    Expects a JSON object with a "status" field ("validated" | "failed"),
    matching the standardized skill output format.
    """
    result = parse_json_output(content)
    status = result.get("status", "")
    if status == "validated":
        return True
    if status == "failed":
        return False
    # Unrecognised format — treat as not validated so signoff retries.
    return False


def _parse_approval_status(content: str) -> str:
    """Extract approval status from agent output.

    Returns "approved" or "changes_requested". Falls back to scanning the
    content for the word "approved" if JSON parsing fails, to guard against
    minor output format deviations.
    """
    result = parse_json_output(content)
    status = result.get("status", "")
    if status in ("approved", "changes_requested"):
        return status
    # Secondary heuristic: look for the keyword in the text
    lower = content.lower()
    if "approved" in lower and "changes_requested" not in lower:
        return "approved"
    return "changes_requested"


def _troubleshooter_descriptor(
    trigger: str, context_path: Path, ctx: "PipelineContext"
) -> dict:
    """Build the exit descriptor for a troubleshooter spawn."""
    return {
        "action": "spawn_agent",
        "message": f"Pipeline issue detected (trigger: {trigger}). Troubleshooter is intervening.",
        "skill": "troubleshooter",
        "trigger": trigger,
        "context_file": str(context_path),
        "cycle_count": ctx.consecutive_failures if trigger == "consecutive_failures"
                       else ctx.signoff_cycle_count if trigger == "signoff_deadlock"
                       else ctx.review_cycle_count,
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
        exit_with_actions([_troubleshooter_descriptor(trigger, context_path, ctx)])


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

class Step(ABC):
    """A single phase of the dev-team pipeline."""

    handles: str

    # Stable event name used by run-event-hooks to resolve before-<event>/after-<event>
    # instructions. None means this Step has no single wrappable agent/script session
    # (e.g. an inline step, or a ParallelSteps composite with no single action of its own)
    # and no "event" key should be added to its emitted descriptors.
    EVENT_NAME: str | None = None

    @abstractmethod
    def get_actions(self) -> list[dict]:
        """Return action descriptors to dispatch. Empty list means inline step."""
        ...

    @abstractmethod
    def handle_results(self) -> str:
        """Process results from the context file and return a trigger moniker."""
        ...


class FindSpecStep(Step):
    handles = "spec-finding"

    def __init__(self, ctx: "PipelineContext") -> None:
        self._ctx = ctx

    def get_actions(self) -> list[dict]:
        """Inline step — no actions needed."""
        return []

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.spec_path:
            return "spec_found"
        spec_file = find_spec_file(ctx.work_item_id)
        ctx.spec_path = str(spec_file.relative_to(REPO_ROOT))
        return "spec_found"


class DebugStep(Step):
    handles = "debugging"
    EVENT_NAME = "debug"

    _PENDING_KEY = "debug"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.debug_report:
            # Result already available — inline step
            return []
        return [{
            "action": "spawn_agent",
            "message": f"Debugger is investigating {ctx.work_item_id}.",
            "agent": "dev-team:debugger",
            "skill": "investigate-bug",
            "context_file": str(self._context_path),
            "args": ctx.work_item_id,
            "read_sections": [],
            "write_section": "Debug Report",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.debug_report:
            _handle_agent_success(ctx)
            status = parse_json_output(ctx.debug_report).get("status", "")
            if status == "reproduced":
                return "debug_done"
            ctx.last_failure = f"Bug could not be reproduced.\n\n{ctx.debug_report}"
            return "reproduction_failed"
        # Agent ran but wrote nothing
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        # If we get here, consecutive_failures has not hit threshold — return failure trigger
        return "reproduction_failed"


class ResearchStep(Step):
    handles = "researching"
    EVENT_NAME = "research"

    _PENDING_KEY = "research"

    def __init__(self, skill: str, ctx: "PipelineContext", context_path: Path) -> None:
        self._skill = skill
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.brief:
            return []
        read_sections = ["Debug Report"] if ctx.debug_report else []
        return [{
            "action": "spawn_agent",
            "message": f"Researcher is planning work for {ctx.work_item_id}.",
            "agent": "dev-team:researcher",
            "skill": self._skill,
            "context_file": str(self._context_path),
            "args": f"{ctx.work_item_id} {ctx.spec_path}",
            "read_sections": read_sections,
            "write_section": "Researcher Brief",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.brief:
            _handle_agent_success(ctx)
            return "research_done"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "research_done"


class ImplementStep(Step):
    handles = "implementing"
    EVENT_NAME = "implement"

    _PENDING_KEY = "implement"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.work_summaries:
            return []
        return [{
            "action": "spawn_agent",
            "message": "Researcher has written the task brief. Developer is now implementing.",
            "agent": "dev-team:developer",
            "skill": "implement-task",
            "args": ctx.work_item_id,
            "context_file": str(self._context_path),
            "read_sections": ["Researcher Brief"],
            "write_section": "Implementation Summary",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.work_summaries:
            _handle_agent_success(ctx)
            return "impl_done"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "impl_done"


class ValidateStep(Step):
    handles = "validating"
    EVENT_NAME = "validate"

    _PENDING_KEY = "validate"

    def __init__(self, ctx: "PipelineContext", context_path: Path, log_dir: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path
        self._log_dir = log_dir

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.validate_result:
            return []
        validate_command = _resolve_validation_script(_project_configuration(ctx), REPO_ROOT)
        if validate_command is None:
            ctx.validate_result = "Succeeded (no validation script configured for this project)"
            return []
        self._log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        log_path = self._log_dir / f"{ctx.work_item_id}-validate-{timestamp}.log"
        ctx.build_log = str(log_path)
        return [{
            "action": "run_script",
            "message": "Running build and test validation.",
            "command": validate_command,
            "log_file": str(log_path),
            "write_section": "Validate Result",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.validate_result:
            result = ctx.validate_result.strip()
            ctx.validate_result = ""
            ctx.pending_agent = ""
            if result.startswith("Succeeded"):
                ctx.last_failure = ""
                if "(no validation script configured for this project)" in result:
                    _commit_and_push(ctx.work_item_id)
                return "clean"
            ctx.last_failure = (
                f"Build or test failures.\n\n"
                f"Full log (read this for details): {ctx.build_log}"
            )
            return "build_failed"
        # Script-runner ran but wrote nothing
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "build_failed"


class CreatePrStep(Step):
    handles = "creating_pr"
    EVENT_NAME = "create-pr"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.pr_url:
            # Recovery re-entry — PR already created
            return []
        read_sections = ["Researcher Brief", "Implementation Summary"]
        for i in range(1, len(ctx.work_summaries)):
            read_sections.append(f"Fix {i}")
        return [{
            "action": "spawn_agent",
            "message": "Implementation complete. Developer is creating a pull request.",
            "agent": "dev-team:developer",
            "skill": "create-pr-from-context",
            "args": ctx.work_item_id,
            "context_file": str(self._context_path),
            "read_sections": read_sections,
            "write_section": "PR URL",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.pr_url:
            # Inline path: already had pr_url
            _handle_agent_success(ctx)
            return "pr_created"
        # Extract pr_url from the JSON the skill wrote to the PR URL section
        text = self._context_path.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        sections = _parse_sections(body)
        pr_url_section = sections.get("PR URL", "")
        if pr_url_section:
            pr_url = parse_json_output(pr_url_section).get("pr_url", "")
            if pr_url:
                ctx.pr_url = pr_url
                _handle_agent_success(ctx)
                ctx.save(self._context_path)
                return "pr_created"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "pr_created"


class ReviewStep(Step):
    handles = "reviewing"
    EVENT_NAME = "review"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.review_notes:
            return []
        return [{
            "action": "spawn_agent",
            "message": "Pull request created. Reviewer is reviewing the changes.",
            "agent": "dev-team:reviewer",
            "skill": "review",
            "context_file": str(self._context_path),
            "read_sections": ["Researcher Brief"],
            "write_section": "Review Notes",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.review_notes:
            _handle_agent_success(ctx)
            status = _parse_approval_status(ctx.review_notes)
            return status
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "changes_requested"


class ParallelSteps(Step):
    """Composite step that dispatches multiple child steps in parallel.

    get_actions() concatenates all children's actions into a single flat list.
    handle_results() calls each child's handle_results() and passes the resulting
    monikers to combine_results().
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


class ReviewerSignOffStep(Step):
    """Wraps the review-sign-off spawn for use inside ParallelSteps."""

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        if self._ctx.signoff_review:
            return []
        return [{
            "action": "spawn_agent",
            "agent": "dev-team:reviewer",
            "skill": "review-sign-off",
            "context_file": str(self._context_path),
            "read_sections": ["Researcher Brief"],
            "write_section": "Signoff Review",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.signoff_review:
            _handle_agent_success(ctx)
            return _parse_approval_status(ctx.signoff_review)
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "changes_requested"


class ResearcherSignOffStep(Step):
    """Wraps the researcher-validate spawn for use inside ParallelSteps."""

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.signoff_research:
            return []
        read_sections = ["Researcher Brief", "Implementation Summary"]
        for i in range(1, len(ctx.work_summaries)):
            read_sections.append(f"Fix {i}")
        return [{
            "action": "spawn_agent",
            "agent": "dev-team:researcher",
            "skill": "researcher-validate",
            "context_file": str(self._context_path),
            "read_sections": read_sections,
            "write_section": "Signoff Research",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.signoff_research:
            _handle_agent_success(ctx)
            return "approved" if _researcher_validated(ctx.signoff_research) else "failed"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "failed"


class BuildValidationStep(Step):
    """Wraps the wait-pr-checks run_script for use inside ParallelSteps."""

    def __init__(self, ctx: "PipelineContext", context_path: Path, log_dir: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path
        self._log_dir = log_dir

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.signoff_build_result:
            return []
        self._log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        log_path = self._log_dir / f"{ctx.work_item_id}-signoff-{timestamp}.log"
        ctx.build_log = str(log_path)
        scripts_dir = Path(__file__).parent
        wait_script = scripts_dir / "wait_pr_checks.py"
        command = f'{sys.executable} "{wait_script}" "{ctx.pr_url}"'
        return [{
            "action": "run_script",
            "command": command,
            "log_file": str(log_path),
            "write_section": "Signoff Build Result",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.signoff_build_result:
            _handle_agent_success(ctx)
            status = parse_json_output(ctx.signoff_build_result).get("status", "")
            return "approved" if status == "passed" else "failed"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "failed"


class SignoffStep(ParallelSteps):
    handles = "signoff"

    def __init__(self, ctx: "PipelineContext", context_path: Path, log_dir: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path
        self._log_dir = log_dir
        super().__init__([
            ReviewerSignOffStep(ctx, context_path),
            ResearcherSignOffStep(ctx, context_path),
            BuildValidationStep(ctx, context_path, log_dir),
        ])

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        # Push first so the reviewer can see the latest commits.
        _commit_and_push(ctx.work_item_id)
        return super().get_actions()

    def handle_results(self) -> str:
        ctx = self._ctx
        trigger = super().handle_results()

        # Build the failure summary for downstream steps
        failures: list[str] = []
        build_status = parse_json_output(ctx.signoff_build_result).get("status", "")
        if build_status != "passed":
            if ctx.signoff_build_result:
                failures.append(
                    f"Build/test validation failed. Log: {ctx.build_log}\n"
                    f"Script result: {ctx.signoff_build_result.strip()}"
                )
        if _parse_approval_status(ctx.signoff_review) != "approved":
            if ctx.signoff_review:
                failures.append(f"Reviewer sign-off:\n{ctx.signoff_review}")
        if not _researcher_validated(ctx.signoff_research):
            if ctx.signoff_research:
                failures.append(f"Research validation:\n{ctx.signoff_research}")

        # Reset sub-step sections for the next signoff cycle
        ctx.signoff_review = ""
        ctx.signoff_research = ""
        ctx.signoff_build_result = ""
        ctx.pending_agent = ""

        if failures or trigger != "approved":
            ctx.review_notes = "\n\n---\n\n".join(failures) if failures else "Signoff failed."
            ctx.last_failure = ctx.review_notes
            return "changes_requested"

        ctx.last_failure = ""
        return "approved"

    def combine_results(self, child_monikers: list[str]) -> str:
        """Signoff: 'failed' > 'changes_requested' > 'approved'."""
        if "failed" in child_monikers:
            return "failed"
        if "changes_requested" in child_monikers:
            return "changes_requested"
        return "approved"


class FixStep(Step):
    handles = "fixing"
    EVENT_NAME = "fix"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        completed = 1 + ctx.fix_iteration + ctx.review_fix_iteration
        if len(ctx.work_summaries) > completed:
            return []
        if ctx.fix_iteration >= MAX_FIX_ITERATIONS:
            return []
        write_section = f"Fix {completed}"
        read_sections = ["Researcher Brief", "Last Failure"]
        if ctx.work_summaries:
            read_sections.append("Implementation Summary")
        for i in range(1, len(ctx.work_summaries)):
            read_sections.append(f"Fix {i}")
        return [{
            "action": "spawn_agent",
            "message": (
                f"Build or tests failed. Developer is fixing "
                f"(iteration {ctx.fix_iteration + 1} of {MAX_FIX_ITERATIONS})."
            ),
            "agent": "dev-team:developer",
            "skill": "fix-draft",
            "args": ctx.work_item_id,
            "context_file": str(self._context_path),
            "read_sections": read_sections,
            "write_section": write_section,
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        completed = 1 + ctx.fix_iteration + ctx.review_fix_iteration
        if len(ctx.work_summaries) > completed:
            _handle_agent_success(ctx)
            ctx.fix_iteration += 1
            return "fix_done"
        if ctx.fix_iteration >= MAX_FIX_ITERATIONS:
            print(
                f"Error: still failing after {MAX_FIX_ITERATIONS} fix iterations. "
                f"Manual intervention needed.",
                file=sys.stderr,
            )
            return "max_retries"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "fix_done"


class FixPrStep(Step):
    handles = "fixing_pr"
    EVENT_NAME = "fix"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        completed = 1 + ctx.fix_iteration + ctx.review_fix_iteration
        if len(ctx.work_summaries) > completed:
            return []
        if ctx.review_fix_iteration >= MAX_REVIEW_FIX_ITERATIONS:
            return []
        write_section = f"Fix {completed}"
        read_sections = ["Researcher Brief", "Review Notes", "Implementation Summary"]
        for i in range(1, len(ctx.work_summaries)):
            read_sections.append(f"Fix {i}")
        # When a PR exists, include failing GitHub Actions check output
        if ctx.pr_url:
            pr_checks_output = _get_failing_pr_checks(ctx.pr_url)
            if pr_checks_output:
                ctx.last_failure = (
                    f"{ctx.review_notes}\n\n"
                    f"Failing GitHub Actions checks:\n```\n{pr_checks_output}\n```"
                )
        return [{
            "action": "spawn_agent",
            "message": (
                f"Review requested changes. Developer is addressing review comments "
                f"(iteration {ctx.review_fix_iteration + 1} of {MAX_REVIEW_FIX_ITERATIONS})."
            ),
            "agent": "dev-team:developer",
            "skill": "fix-pr",
            "args": ctx.work_item_id,
            "context_file": str(self._context_path),
            "read_sections": read_sections,
            "write_section": write_section,
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        completed = 1 + ctx.fix_iteration + ctx.review_fix_iteration
        if len(ctx.work_summaries) > completed:
            _handle_agent_success(ctx)
            ctx.review_fix_iteration += 1
            ctx.review_notes = ""  # ensure ReviewStep re-runs reviewer on next cycle
            return "fix_done"
        if ctx.review_fix_iteration >= MAX_REVIEW_FIX_ITERATIONS:
            print(
                f"Error: still failing review after {MAX_REVIEW_FIX_ITERATIONS} "
                f"review fix iterations. Manual intervention needed.",
                file=sys.stderr,
            )
            return "max_retries"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "fix_done"


class HandoffStep(Step):
    """Runs only once `signoff` has approved — `reviewing`'s own `approved` trigger routes
    to `signoff`, never here directly, so every hand-off is preceded by a full signoff pass.

    Its event is named `signoff` (not `handoff`) because the pipeline event a project's
    `instructions:` config customizes around this step is `before-signoff`/
    `after-signoff-success`/`after-signoff-failure` — the hand-off work (promote PR, request
    review, assign the work item) is configured as `after-signoff-success` instructions, run
    generically by `run-event-hooks` around this near-no-op dispatch.
    """

    handles = "handoff"
    EVENT_NAME = "signoff"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.handoff_result:
            return []
        return [{
            "action": "spawn_agent",
            "message": "Signoff approved. Developer is handing off to a human reviewer.",
            "agent": "dev-team:developer",
            "skill": "final-sign-off",
            "args": f"{ctx.pr_url} {ctx.work_item_id}",
            "context_file": str(self._context_path),
            "read_sections": [],
            "write_section": "Handoff Result",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.handoff_result:
            _handle_agent_success(ctx)
            return "handoff_done"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "handoff_done"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class DevTeamPipeline:
    """Drives the dev-team state machine from init (or a resumed state) to done."""

    def __init__(
        self,
        ctx: PipelineContext,
        context_path: Path,
        log_dir: Path,
        workflow: WorkflowDefinition,
        research_skill: str,
    ) -> None:
        self.ctx = ctx
        self.context_path = context_path
        self.log_dir = log_dir
        self.workflow = workflow
        self.machine = StateMachine(workflow.transitions, initial=ctx.state)
        self.step_handlers: dict[str, Step] = {
            "spec-finding": FindSpecStep(ctx),
            "debugging": DebugStep(ctx, context_path),
            "researching": ResearchStep(research_skill, ctx, context_path),
            "implementing": ImplementStep(ctx, context_path),
            "validating": ValidateStep(ctx, context_path, log_dir),
            "fixing": FixStep(ctx, context_path),
            "creating_pr": CreatePrStep(ctx, context_path),
            "reviewing": ReviewStep(ctx, context_path),
            "signoff": SignoffStep(ctx, context_path, log_dir),
            "fixing_pr": FixPrStep(ctx, context_path),
            "handoff": HandoffStep(ctx, context_path),
        }

    def _dispatch_step(self, step: Step) -> str:
        """Dispatch a step: get actions, exit if non-empty, else return trigger inline."""
        return self._do_get_actions_and_exit(step)

    def _do_get_actions_and_exit(self, step: Step) -> str:
        """Call get_actions(); exit if non-empty; otherwise call handle_results()."""
        actions = step.get_actions()
        if actions:
            event_name = getattr(step, "EVENT_NAME", None)
            if event_name:
                for action in actions:
                    action["event"] = event_name
            self.ctx.pending_agent = _step_pending_key(step)
            self.ctx.save(self.context_path)
            exit_with_actions(actions)
        # Inline step
        return step.handle_results()

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

            _apply_counter_updates(self.ctx, current_state, trigger)

            # Check trigger-based troubleshooter conditions
            if self.ctx.signoff_cycle_count >= SIGNOFF_DEADLOCK_THRESHOLD:
                self.ctx.save(self.context_path)
                exit_with_actions([_troubleshooter_descriptor(
                    "signoff_deadlock", self.context_path, self.ctx
                )])

            if self.ctx.review_cycle_count >= REVIEW_LOOP_THRESHOLD:
                self.ctx.save(self.context_path)
                exit_with_actions([_troubleshooter_descriptor(
                    "review_loop", self.context_path, self.ctx
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


def _step_pending_key(step: Step) -> str:
    """Return the pending_agent key for a step, falling back to handles."""
    if hasattr(step, "_PENDING_KEY"):
        return step._PENDING_KEY  # type: ignore[attr-defined]
    if hasattr(step, "handles"):
        return step.handles
    return ""


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


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body. Returns (metadata_dict, body)."""
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




def find_spec_file(work_item_id: str) -> Path:
    """Find the unique _spec_*.md file that contains the work item ID."""
    candidates = [
        p
        for p in REPO_ROOT.rglob("_spec_*.md")
        if ".git" not in p.parts
    ]

    matches = [
        p for p in candidates
        if work_item_id in p.read_text(encoding="utf-8")
    ]

    if not matches:
        print(
            f"Error: no _spec_*.md file found containing '{work_item_id}'.\n"
            f"Verify the task key is correct and you are on the right branch.",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(matches) > 1:
        paths = "\n  ".join(str(m.relative_to(REPO_ROOT)) for m in matches)
        print(
            f"Error: multiple spec files found containing '{work_item_id}' — "
            f"cannot determine which to use:\n  {paths}\n"
            f"Resolve the ambiguity (e.g. deduplicate the task key) and retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    return matches[0]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dev_team.py",
        description="dev-team pipeline step machine",
    )
    parser.add_argument("work_item_id", metavar="work-item-id",
                        help="Work item ID (e.g. ADR-172 or Issue-444)")
    parser.add_argument("--workflow", metavar="path", default=None,
                        help="Path to a Mermaid stateDiagram-v2 workflow file")
    parser.add_argument("--research-skill", metavar="skill", default=None,
                        help="Researcher skill to use (e.g. plan-task or researcher-issue)")
    parser.add_argument("--plugin-root", metavar="path", default=None,
                        help="Plugin installation root (agents/ and commands/ resolved here)")
    parser.add_argument("--context-file", metavar="path", default=None,
                        help="Path to the pipeline context file (computed by dev-team.md)")
    parser.add_argument("--print-context-path", metavar="repo-slug", default=None,
                        help="Print the context file path for the given repo slug and exit")
    args = parser.parse_args()

    # --print-context-path mode: compute and print the context file path, then exit.
    if args.print_context_path is not None:
        print(compute_context_path(args.work_item_id, args.print_context_path), flush=True)
        sys.exit(0)

    # Normal pipeline mode requires --workflow, --research-skill, and --context-file.
    if not args.workflow:
        parser.error("--workflow is required")
    if not args.research_skill:
        parser.error("--research-skill is required")
    if not args.context_file:
        parser.error("--context-file is required")

    work_item_id = args.work_item_id
    workflow_path = Path(args.workflow)
    if not workflow_path.is_absolute():
        workflow_path = REPO_ROOT / workflow_path

    try:
        workflow = parse_workflow(workflow_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading workflow: {e}", file=sys.stderr)
        sys.exit(1)

    context_path = Path(args.context_file)
    log_dir = context_path.parent / "logs"

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

    DevTeamPipeline(
        ctx, context_path, log_dir, workflow,
        research_skill=args.research_skill,
    ).run()


if __name__ == "__main__":
    main()
