#!/usr/bin/env python3
"""implement/fix task-pipeline steps.

Entry point: main() — accepts a Jira work item ID and context file path, runs the
implement/fix task pipeline until an agent is needed, then exits with a JSON descriptor on
stdout (exit code 0). The workflow-orchestrate skill re-invokes this script after each
agent run. Shared with fix-issue-plan.md — both workflow assets use this exact step_handlers
map; only the mermaid diagram (which states are reachable, in what order) differs between
implement-task-plan.md and fix-issue-plan.md.
"""

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

import dev_team
from dev_team import (
    REPO_ROOT,
    CONSECUTIVE_FAILURES_THRESHOLD,
    ParallelSteps,
    Step,
    _check_and_trigger_troubleshooter,
    _handle_agent_failure,
    _handle_agent_success,
    _parse_frontmatter,
    _parse_sections,
    _project_configuration,
    parse_json_output,
)
from pipeline_context import PipelineContext

MAX_FIX_ITERATIONS = 5
MAX_REVIEW_FIX_ITERATIONS = 3
SIGNOFF_DEADLOCK_THRESHOLD = 2
REVIEW_LOOP_THRESHOLD = MAX_REVIEW_FIX_ITERATIONS


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
# Steps
# ---------------------------------------------------------------------------

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
    """Runs the `/fix` pipeline's `researching` state — investigates a bug report via the
    `dev-team:researcher` agent's `researcher-issue` skill. See `PlanStep` for the `/implement`
    pipeline's counterpart, which hardcodes a different agent+skill pair for spec-driven tasks."""

    handles = "researching"
    EVENT_NAME = "research"

    _PENDING_KEY = "research"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
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
            "skill": "researcher-issue",
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


class PlanStep(Step):
    """Runs the `/implement` pipeline's `planning` state — turns a spec section into a task
    brief via the `dev-team:planner` agent's `plan-task` skill, restricted to the spec and the
    local codebase (no external research). See `ResearchStep` for the `/fix` pipeline's
    counterpart.

    `handle_results()` always returns `"ready"` today — there is no `research_needed` branch
    wired up yet; this is the fork point a future research loop would use."""

    handles = "planning"
    EVENT_NAME = "plan"

    _PENDING_KEY = "planning"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.brief:
            return []
        return [{
            "action": "spawn_agent",
            "message": f"Planner is planning work for {ctx.work_item_id}.",
            "agent": "dev-team:planner",
            "skill": "plan-task",
            "context_file": str(self._context_path),
            "args": f"{ctx.work_item_id} {ctx.spec_path}",
            "read_sections": [],
            "write_section": "Researcher Brief",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.brief:
            _handle_agent_success(ctx)
            return "ready"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "ready"


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
            "message": "Task brief is ready. Developer is now implementing.",
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
    """Runs the three signoff checks in parallel, then resolves to `"approved"` or
    `"changes_requested"`. Carries `EVENT_NAME = "signoff"` directly (rather than a
    downstream near-no-op hand-off step) — the pipeline already knows exactly when this
    resolves, so a project's `before-signoff`/`after-signoff-approved` instructions (e.g.
    promoting the PR, requesting review) hang directly off this step's own trigger."""

    handles = "signoff"
    EVENT_NAME = "signoff"

    def __init__(self, ctx: "PipelineContext", context_path: Path, log_dir: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path
        self._log_dir = log_dir
        super().__init__([
            ReviewerSignOffStep(ctx, context_path),
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


class AddToPrStackStep(Step):
    """Runs once `signoff` resolves `approved`: registers this task's already-signed-off PR into
    its epic's `gh stack` via `add-to-pr-stack` (`gh stack link`) — the sole place that
    registration ever happens (see that skill's own intro, and `ensure-working-branch`'s, for why
    it's deferred this late rather than done eagerly at task start).

    No dedicated retry edge exists from `add_to_pr_stack` in the state machine (mirroring
    `creating_pr`'s own precedent) — a hard failure here still proceeds to `done` with
    `added_to_stack` left `false`, relying on `consecutive_failures`/the troubleshooter for
    escalation rather than looping the state machine itself. This task's own epic stack is left
    missing one entry until someone (or the troubleshooter) re-runs this step by hand; that's a
    silent gap worth watching for, not a design this step tries to paper over.

    `add_to_pr_stack.py` (the script `add-to-pr-stack`'s own SKILL.md runs) always writes a
    `stack_link_status` extra-frontmatter key on success — `"linked"` or `"not_applicable"` — even
    though `added_to_stack` itself only ever becomes `True` for the former. This is deliberately
    checked ahead of `added_to_stack` below: `added_to_stack` alone can't distinguish "resolved,
    nothing to register" from "never ran yet" (it's a plain boolean that only ever needs to become
    `True`), which would otherwise leave `get_actions()` re-spawning the agent forever for a task
    that legitimately isn't part of any tracked epic.
    """

    handles = "add_to_pr_stack"
    EVENT_NAME = "add-to-pr-stack"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.added_to_stack or ctx.extra_frontmatter.get("stack_link_status"):
            # Recovery re-entry — already registered, or already determined not applicable.
            return []
        return [{
            "action": "spawn_agent",
            "message": "Sign-off approved. Developer is registering the PR into its epic's stack.",
            "agent": "dev-team:developer",
            "skill": "add-to-pr-stack",
            "args": ctx.work_item_id,
            "context_file": str(self._context_path),
            "read_sections": [],
            "write_section": "Stack Link Result",
            "result_format": "success | failed",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if ctx.added_to_stack or ctx.extra_frontmatter.get("stack_link_status"):
            # Inline path: the script's own direct frontmatter write already landed before this
            # function's own re-entry — the primary, common-case path, since add_to_pr_stack.py
            # (unlike an LLM-composed deliverable) never "forgets" to persist its result.
            _handle_agent_success(ctx)
            return "linked"
        # Fallback, mirroring CreatePrStep's own "PR URL" section fallback: the frontmatter write
        # somehow didn't land, but the agent did write the Stack Link Result section.
        text = self._context_path.read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        sections = _parse_sections(body)
        result_section = sections.get("Stack Link Result", "")
        if result_section:
            status = parse_json_output(result_section).get("status", "")
            if status in ("linked", "not_applicable"):
                _handle_agent_success(ctx)
                return "linked"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "linked"


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


# ---------------------------------------------------------------------------
# step_handlers factory
# ---------------------------------------------------------------------------

def _build_step_handlers(
    ctx: "PipelineContext", context_path: Path, log_dir: Path,
) -> dict[str, Step]:
    return {
        "spec-finding": FindSpecStep(ctx),
        "debugging": DebugStep(ctx, context_path),
        "researching": ResearchStep(ctx, context_path),
        "planning": PlanStep(ctx, context_path),
        "implementing": ImplementStep(ctx, context_path),
        "validating": ValidateStep(ctx, context_path, log_dir),
        "fixing": FixStep(ctx, context_path),
        "creating_pr": CreatePrStep(ctx, context_path),
        "reviewing": ReviewStep(ctx, context_path),
        "signoff": SignoffStep(ctx, context_path, log_dir),
        "add_to_pr_stack": AddToPrStackStep(ctx, context_path),
        "fixing_pr": FixPrStep(ctx, context_path),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="implement.py",
        description="implement/fix task-pipeline step machine",
    )
    parser.add_argument("work_item_id", metavar="work-item-id",
                        help="Work item ID (e.g. ADR-172 or Issue-444)")
    parser.add_argument("--workflow", metavar="path", default=None,
                        help="Path to a Mermaid stateDiagram-v2 workflow file")
    parser.add_argument("--plugin-root", metavar="path", default=None,
                        help="Plugin installation root (agents/ and commands/ resolved here)")
    parser.add_argument("--context-file", metavar="path", default=None,
                        help="Path to the pipeline context file (computed by get_context_path.py)")
    parser.add_argument("--print-context-path", metavar="repo-slug", default=None,
                        help="Print the context file path for the given repo slug and exit")
    args = parser.parse_args()

    if args.print_context_path is not None:
        print(dev_team.compute_context_path(args.work_item_id, args.print_context_path), flush=True)
        sys.exit(0)

    if not args.workflow:
        parser.error("--workflow is required")
    if not args.context_file:
        parser.error("--context-file is required")

    work_item_id = args.work_item_id
    workflow_path = Path(args.workflow)
    if not workflow_path.is_absolute():
        workflow_path = REPO_ROOT / workflow_path

    context_path = Path(args.context_file)
    log_dir = context_path.parent / "logs"

    dev_team.run_pipeline(
        work_item_id,
        workflow_path,
        context_path,
        step_handlers_factory=lambda ctx, cp: _build_step_handlers(ctx, cp, log_dir),
        counter_updater=_apply_counter_updates,
        troubleshooter_checks=[
            ("signoff_cycle_count", SIGNOFF_DEADLOCK_THRESHOLD, "signoff_deadlock"),
            ("review_cycle_count", REVIEW_LOOP_THRESHOLD, "review_loop"),
        ],
    )


if __name__ == "__main__":
    main()
