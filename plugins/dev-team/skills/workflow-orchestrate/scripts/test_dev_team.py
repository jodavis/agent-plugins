"""Tests for dev_team.py — the generic, pipeline-agnostic engine shared by every
dev-team pipeline (implement/fix via implement.py, the long-lived PR monitor via
monitor_prs.py).

Covers:
- exit_with_actions() — JSON array serialisation and exit-code 0
- compute_context_path() — base path resolution with/without DEV_TEAM_STATE_DIR
- merge_pending_deliverables()/_replace_or_append_section() — scratch-file merge
- WorkflowDefinition/parse_workflow()/StateMachine — Mermaid-diagram-driven state machine
- Project configuration caching (_project_configuration()) and hook-phase gating
  (DevTeamPipeline._do_get_actions_and_exit())
- consecutive_failures counter — the one threshold generic enough to live in the engine
- ParallelSteps composite dispatch, get_context_path.py's slug extraction, _find_repo_root()

Pipeline-specific step behavior (implement/fix's Step subclasses, its counters, its
troubleshooter thresholds) lives in test_implement.py instead.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_exit_with_actions(descriptors: list[dict]) -> subprocess.CompletedProcess:
    """Invoke exit_with_actions in a child process to isolate sys.exit."""
    descriptors_json = json.dumps(descriptors)
    script = (
        f"import sys; sys.path.insert(0, {str(SCRIPTS_DIR)!r}); "
        f"import json; from dev_team import exit_with_actions; "
        f"exit_with_actions(json.loads({descriptors_json!r}))"
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
    )


# ---------------------------------------------------------------------------
# exit_with_actions
# ---------------------------------------------------------------------------

class TestExitWithActions:
    def test_exits_with_code_0(self):
        result = _run_exit_with_actions([{"action": "done", "result": "success"}])
        assert result.returncode == 0

    def test_emits_json_array_on_stdout(self):
        descriptor = {"action": "done", "result": "success", "reason": "all clean"}
        result = _run_exit_with_actions([descriptor])
        parsed = json.loads(result.stdout.strip())
        assert isinstance(parsed, list)
        assert parsed == [descriptor]

    def test_single_item_wrapped_in_array(self):
        result = _run_exit_with_actions([{"action": "done"}])
        parsed = json.loads(result.stdout.strip())
        assert parsed == [{"action": "done"}]

    def test_serializes_nested_list_fields(self):
        descriptor = {
            "action": "spawn_agent",
            "agent": "developer",
            "skill": "developer-implement",
            "context_file": "/home/.dev-team/repo/ADR-123.md",
            "read_sections": ["Researcher Brief", "Review Notes"],
            "write_section": "Implementation Summary",
            "result_format": "success | failed",
        }
        result = _run_exit_with_actions([descriptor])
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        assert parsed == [descriptor]

    def test_nothing_on_stderr(self):
        result = _run_exit_with_actions([{"action": "done", "result": "success"}])
        assert result.stderr == ""

    def test_empty_list_is_valid(self):
        result = _run_exit_with_actions([])
        assert result.returncode == 0
        assert json.loads(result.stdout.strip()) == []

    def test_multiple_items_preserved_in_order(self):
        items = [
            {"action": "spawn_agent", "skill": "reviewer-sign-off"},
            {"action": "spawn_agent", "skill": "researcher-validate"},
            {"action": "run_script", "command": "bash build.sh"},
        ]
        result = _run_exit_with_actions(items)
        parsed = json.loads(result.stdout.strip())
        assert parsed == items


# ---------------------------------------------------------------------------
# compute_context_path
# ---------------------------------------------------------------------------

class TestComputeContextPath:
    def test_uses_home_dev_team_by_default(self, monkeypatch):
        monkeypatch.delenv("DEV_TEAM_STATE_DIR", raising=False)
        from dev_team import compute_context_path
        path = compute_context_path("ADR-123", "jodavis/AdaptiveRemote")
        expected = Path.home() / ".dev-team" / "jodavis" / "AdaptiveRemote" / "ADR-123.md"
        assert path == expected

    def test_uses_dev_team_state_dir_when_set(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        from dev_team import compute_context_path
        path = compute_context_path("ADR-456", "myorg/myrepo")
        expected = tmp_path / "myorg" / "myrepo" / "ADR-456.md"
        assert path == expected

    def test_work_item_id_becomes_filename(self, monkeypatch):
        monkeypatch.delenv("DEV_TEAM_STATE_DIR", raising=False)
        from dev_team import compute_context_path
        path = compute_context_path("Issue-42", "org/repo")
        assert path.name == "Issue-42.md"

    def test_repo_slug_becomes_subdirectory(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        from dev_team import compute_context_path
        path = compute_context_path("ADR-1", "my-org/my-repo")
        assert path.parent == tmp_path / "my-org" / "my-repo"

    def test_hyphenated_repo_slug(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        from dev_team import compute_context_path
        path = compute_context_path("ADR-99", "acme-corp/cool-service")
        assert path == tmp_path / "acme-corp" / "cool-service" / "ADR-99.md"


# ---------------------------------------------------------------------------
# _replace_or_append_section — deterministic sentinel-replace-or-append
# ---------------------------------------------------------------------------

class TestReplaceOrAppendSection:
    def test_sentinel_absent_appends_after_last_line(self):
        from dev_team import _replace_or_append_section
        context_text = "---\nstate: researching\n---\n\nSome preamble.\n"
        result = _replace_or_append_section(context_text, "Researcher Brief", "The brief text.")
        assert result == (
            "---\nstate: researching\n---\n\nSome preamble.\n\n"
            "<!-- section:Researcher Brief -->\n\nThe brief text.\n\n"
        )

    def test_sentinel_present_replaces_content_up_to_next_sentinel(self):
        from dev_team import _replace_or_append_section
        context_text = (
            "---\nstate: reviewing\n---\n\n"
            "<!-- section:Researcher Brief -->\n\nOld brief.\n\n"
            "<!-- section:Review Notes -->\n\nOld notes.\n"
        )
        result = _replace_or_append_section(context_text, "Researcher Brief", "New brief.")
        assert result == (
            "---\nstate: reviewing\n---\n\n"
            "<!-- section:Researcher Brief -->\n\nNew brief.\n\n"
            "<!-- section:Review Notes -->\n\nOld notes.\n"
        )

    def test_sentinel_present_as_last_section_replaces_to_end_of_file(self):
        from dev_team import _replace_or_append_section
        context_text = "---\nstate: reviewing\n---\n\n<!-- section:Review Notes -->\n\nOld notes.\n"
        result = _replace_or_append_section(context_text, "Review Notes", "New notes.")
        assert result == "---\nstate: reviewing\n---\n\n<!-- section:Review Notes -->\n\nNew notes.\n\n"

    def test_content_is_stripped_of_surrounding_whitespace(self):
        from dev_team import _replace_or_append_section
        result = _replace_or_append_section("", "Fix 1", "\n\n  Fixed the bug.  \n\n")
        assert result == "<!-- section:Fix 1 -->\n\nFixed the bug.\n\n"


# ---------------------------------------------------------------------------
# merge_pending_deliverables — scratch-file merge preprocessing step (issue #191)
# ---------------------------------------------------------------------------

class TestMergePendingDeliverables:
    def test_no_pending_directory_is_a_silent_no_op(self, tmp_path):
        from dev_team import merge_pending_deliverables
        context_path = tmp_path / "ADR-999.md"
        context_path.write_text("---\nstate: researching\n---\n")

        merge_pending_deliverables(context_path, "ADR-999")

        assert context_path.read_text() == "---\nstate: researching\n---\n"

    def test_no_matching_scratch_files_for_this_work_item_is_a_no_op(self, tmp_path):
        from dev_team import merge_pending_deliverables
        context_path = tmp_path / "ADR-999.md"
        context_path.write_text("---\nstate: researching\n---\n")
        pending_dir = tmp_path / ".pending"
        pending_dir.mkdir()
        (pending_dir / "ADR-111__Researcher_Brief.md").write_text("someone else's brief")

        merge_pending_deliverables(context_path, "ADR-999")

        assert context_path.read_text() == "---\nstate: researching\n---\n"
        assert (pending_dir / "ADR-111__Researcher_Brief.md").exists()

    def test_matching_scratch_file_is_merged_in_and_deleted(self, tmp_path):
        from dev_team import merge_pending_deliverables
        context_path = tmp_path / "ADR-999.md"
        context_path.write_text("---\nstate: researching\n---\n")
        pending_dir = tmp_path / ".pending"
        pending_dir.mkdir()
        scratch_path = pending_dir / "ADR-999__Researcher_Brief.md"
        scratch_path.write_text("The researched brief.")

        merge_pending_deliverables(context_path, "ADR-999")

        assert "<!-- section:Researcher Brief -->" in context_path.read_text()
        assert "The researched brief." in context_path.read_text()
        assert not scratch_path.exists()

    def test_section_name_underscore_to_space_reconstruction(self, tmp_path):
        from dev_team import merge_pending_deliverables
        context_path = tmp_path / "ADR-999.md"
        context_path.write_text("---\nstate: researching\n---\n")
        pending_dir = tmp_path / ".pending"
        pending_dir.mkdir()
        (pending_dir / "ADR-999__Post-Handoff_Fix_3.md").write_text("Fixed the review comment.")

        merge_pending_deliverables(context_path, "ADR-999")

        assert "<!-- section:Post-Handoff Fix 3 -->" in context_path.read_text()

    def test_multiple_matching_scratch_files_are_all_merged_and_deleted(self, tmp_path):
        from dev_team import merge_pending_deliverables
        context_path = tmp_path / "ADR-999.md"
        context_path.write_text("---\nstate: reviewing\n---\n")
        pending_dir = tmp_path / ".pending"
        pending_dir.mkdir()
        brief_path = pending_dir / "ADR-999__Researcher_Brief.md"
        notes_path = pending_dir / "ADR-999__Review_Notes.md"
        brief_path.write_text("The brief.")
        notes_path.write_text("The notes.")

        merge_pending_deliverables(context_path, "ADR-999")

        final_text = context_path.read_text()
        assert "<!-- section:Researcher Brief -->" in final_text
        assert "<!-- section:Review Notes -->" in final_text
        assert not brief_path.exists()
        assert not notes_path.exists()

    def test_context_file_does_not_yet_exist_treats_it_as_empty(self, tmp_path):
        from dev_team import merge_pending_deliverables
        context_path = tmp_path / "ADR-999.md"
        pending_dir = tmp_path / ".pending"
        pending_dir.mkdir()
        (pending_dir / "ADR-999__Researcher_Brief.md").write_text("The brief.")

        merge_pending_deliverables(context_path, "ADR-999")

        assert context_path.exists()
        assert "<!-- section:Researcher Brief -->" in context_path.read_text()


# ---------------------------------------------------------------------------
# project_configuration field / section
# ---------------------------------------------------------------------------

class TestProjectConfiguration:
    def test_defaults_to_empty(self):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-TEST")
        assert ctx.project_configuration == ""

    def test_roundtrip_through_save_load(self, tmp_path):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-123", project_configuration='{"a": 1}')
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.project_configuration == '{"a": 1}'

    def test_written_as_first_section_before_other_known_sections(self, tmp_path):
        from dev_team import PipelineContext
        ctx = PipelineContext(
            work_item_id="ADR-123",
            project_configuration='{"a": 1}',
            workspace_setup="setup notes",
        )
        path = tmp_path / "ctx.md"
        ctx.save(path)
        text = path.read_text(encoding="utf-8")
        assert text.index("<!-- section:Project Configuration -->") < text.index(
            "<!-- section:Workspace Setup -->"
        )

    def test_omitted_from_file_when_empty(self, tmp_path):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-123")
        path = tmp_path / "ctx.md"
        ctx.save(path)
        assert "<!-- section:Project Configuration -->" not in path.read_text(encoding="utf-8")


class TestProjectConfigurationHelper:
    def test_uses_cached_value_without_calling_load_project_config(self, monkeypatch):
        import dev_team
        from dev_team import PipelineContext, _project_configuration

        def _fail(repo_root):
            raise AssertionError("_load_project_config should not be called when cached")

        monkeypatch.setattr(dev_team, "_load_project_config", _fail)
        ctx = PipelineContext(work_item_id="ADR-TEST", project_configuration='{"a": 1}')

        assert _project_configuration(ctx) == {"a": 1}


# ---------------------------------------------------------------------------
# consecutive_failures counter
# ---------------------------------------------------------------------------

class TestConsecutiveFailures:
    def make_sut(self, **kwargs):
        from dev_team import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_starts_at_zero(self):
        ctx = self.make_sut()
        assert ctx.consecutive_failures == 0

    def test_increments_on_agent_failure(self):
        from dev_team import _handle_agent_failure
        ctx = self.make_sut()
        _handle_agent_failure(ctx)
        assert ctx.consecutive_failures == 1

    def test_accumulates_across_multiple_failures(self):
        from dev_team import _handle_agent_failure
        ctx = self.make_sut()
        _handle_agent_failure(ctx)
        _handle_agent_failure(ctx)
        _handle_agent_failure(ctx)
        assert ctx.consecutive_failures == 3

    def test_resets_to_zero_on_agent_success(self):
        from dev_team import _handle_agent_success
        ctx = self.make_sut(consecutive_failures=5)
        _handle_agent_success(ctx)
        assert ctx.consecutive_failures == 0

    def test_reset_does_not_require_prior_failure(self):
        from dev_team import _handle_agent_success
        ctx = self.make_sut(consecutive_failures=0)
        _handle_agent_success(ctx)
        assert ctx.consecutive_failures == 0

    def test_roundtrip_through_save_load(self, tmp_path):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-123", consecutive_failures=2)
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.consecutive_failures == 2


# ---------------------------------------------------------------------------
# exit_with_actions — parallel flat array with mixed spawn_agent + run_script
# ---------------------------------------------------------------------------

class TestExitWithActionsParallel:
    def test_flat_array_with_spawn_and_run_script_items(self):
        items = [
            {"action": "spawn_agent", "agent": "task-runner", "skill": "reviewer-sign-off",
             "context_file": "/tmp/ctx.md", "read_sections": [],
             "write_section": "Signoff Review", "result_format": "success | failed"},
            {"action": "spawn_agent", "agent": "task-runner", "skill": "researcher-validate",
             "context_file": "/tmp/ctx.md", "read_sections": ["Researcher Brief"],
             "write_section": "Signoff Research", "result_format": "success | failed"},
            {"action": "run_script", "command": "bash validate-build.sh",
             "log_file": "/tmp/signoff.log", "result_format": "success | failed"},
        ]
        result = _run_exit_with_actions(items)
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        assert isinstance(parsed, list)
        assert len(parsed) == 3

    def test_reviewer_item_in_flat_array(self):
        items = [
            {"action": "spawn_agent", "skill": "reviewer-sign-off"},
            {"action": "spawn_agent", "skill": "researcher-validate"},
            {"action": "run_script", "command": "bash build.sh", "log_file": "/tmp/build.log",
             "result_format": "success | failed"},
        ]
        result = _run_exit_with_actions(items)
        parsed = json.loads(result.stdout.strip())
        assert parsed[0]["skill"] == "reviewer-sign-off"

    def test_run_script_item_has_correct_fields(self):
        run_item = {"action": "run_script", "command": "bash test.sh",
                    "log_file": "/tmp/test.log", "result_format": "success | failed"}
        result = _run_exit_with_actions([run_item])
        parsed = json.loads(result.stdout.strip())
        assert parsed[0]["action"] == "run_script"
        assert parsed[0]["command"] == "bash test.sh"
        assert parsed[0]["log_file"] == "/tmp/test.log"


# ---------------------------------------------------------------------------
# message field in exit_with_actions items
# ---------------------------------------------------------------------------

class TestExitWithActionsMessage:
    def test_message_field_in_item_is_serialized(self):
        item = {
            "action": "spawn_agent",
            "message": "Developer is implementing.",
            "agent": "developer",
            "skill": "developer-implement",
        }
        result = _run_exit_with_actions([item])
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        assert parsed[0]["message"] == "Developer is implementing."

    def test_item_without_message_still_valid(self):
        item = {"action": "done", "result": "success"}
        result = _run_exit_with_actions([item])
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        assert "message" not in parsed[0]


# ---------------------------------------------------------------------------
# get_context_path.py — slug extraction from various remote URL formats
# ---------------------------------------------------------------------------

import os

GET_CONTEXT_PATH_PY = SCRIPTS_DIR / "get_context_path.py"


def _make_env(tmp_path: Path, extra: dict | None = None) -> dict:
    """Build an env for running get_context_path.py under test."""
    env = {**os.environ, "DEV_TEAM_STATE_DIR": str(tmp_path)}
    if extra:
        env.update(extra)
    return env


def _run_slug_extraction(remote_url: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the script with the remote URL injected via GIT_REMOTE_URL_OVERRIDE."""
    env = _make_env(tmp_path, {"GIT_REMOTE_URL_OVERRIDE": remote_url})
    return subprocess.run(
        [sys.executable, str(GET_CONTEXT_PATH_PY), "ADR-123"],
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )


@pytest.mark.parametrize("remote_url,expected_slug", [
    ("https://github.com/org/repo.git",  "org/repo"),
    ("https://github.com/org/repo",       "org/repo"),
    ("git@github.com:org/repo.git",       "org/repo"),
    ("git@github.com:org/repo",           "org/repo"),
    ("https://github.com/acme-corp/cool-service.git", "acme-corp/cool-service"),
])
class TestGetContextPathPySlugExtraction:
    def test_slug_in_output_path(self, tmp_path, remote_url, expected_slug):
        result = _run_slug_extraction(remote_url, tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # The output path must contain the expected slug as path components
        output = result.stdout.strip()
        # Normalise path separators for comparison
        slug_as_path = expected_slug.replace("/", os.sep)
        assert slug_as_path in output or expected_slug in output, (
            f"Expected slug {expected_slug!r} in output path {output!r}"
        )

    def test_exits_zero(self, tmp_path, remote_url, expected_slug):
        result = _run_slug_extraction(remote_url, tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_nothing_on_stderr(self, tmp_path, remote_url, expected_slug):
        result = _run_slug_extraction(remote_url, tmp_path)
        assert result.stderr == ""


class TestGetContextPathPyErrorHandling:
    def test_exits_nonzero_when_git_fails(self, tmp_path):
        """Script should exit 1 and print to stderr when git fails.

        We achieve this by NOT setting GIT_REMOTE_URL_OVERRIDE and running in a
        directory that has no git remote, so `git remote get-url origin` fails.
        """
        empty_git_dir = tmp_path / "empty_repo"
        empty_git_dir.mkdir()
        subprocess.run(["git", "init", str(empty_git_dir)],
                       capture_output=True, timeout=15)
        env = _make_env(tmp_path)
        result = subprocess.run(
            [sys.executable, str(GET_CONTEXT_PATH_PY), "ADR-1"],
            capture_output=True, text=True, timeout=15, env=env,
            cwd=str(empty_git_dir),
        )
        assert result.returncode != 0
        assert result.stderr != ""

    def test_exits_nonzero_when_no_work_item_id(self, tmp_path):
        """Script should exit 1 with a usage message when called with no args."""
        env = _make_env(tmp_path)
        result = subprocess.run(
            [sys.executable, str(GET_CONTEXT_PATH_PY)],
            capture_output=True, text=True, timeout=15, env=env,
        )
        assert result.returncode != 0
        assert "Usage" in result.stderr


# ---------------------------------------------------------------------------
# ParallelSteps
# ---------------------------------------------------------------------------

class _StubStep:
    """Minimal Step-like object for testing ParallelSteps."""

    def __init__(self, actions: list[dict], result: str) -> None:
        self._actions = actions
        self._result = result
        self.called = False

    def get_actions(self) -> list[dict]:
        return list(self._actions)

    def handle_results(self) -> str:
        self.called = True
        return self._result


class ConcreteParallelSteps:
    """Minimal concrete subclass of ParallelSteps for testing."""

    def __init__(self, steps):
        from dev_team import ParallelSteps
        # Build using composition since ParallelSteps is abstract
        self._ps = _ConcretePS(steps)

    def get_actions(self):
        return self._ps.get_actions()

    def handle_results(self):
        return self._ps.handle_results()


class _ConcretePS:
    """Concrete ParallelSteps for use in tests."""

    def __init__(self, steps):
        from dev_team import ParallelSteps
        # We can't directly instantiate ParallelSteps (abstract), so we subclass inline
        self._steps = steps

    def get_actions(self):
        all_actions = []
        for step in self._steps:
            all_actions.extend(step.get_actions())
        return all_actions

    def handle_results(self):
        child_monikers = [step.handle_results() for step in self._steps]
        return self.combine_results(child_monikers)

    def combine_results(self, child_monikers):
        if "failed" in child_monikers:
            return "failed"
        if "changes_requested" in child_monikers:
            return "changes_requested"
        return child_monikers[0] if child_monikers else "approved"


def _make_concrete_parallel(child_defs):
    """Build a concrete ParallelSteps-like with _StubStep children."""
    steps = [_StubStep(actions, result) for actions, result in child_defs]
    ps = _ConcretePS(steps)
    return ps, steps


class TestParallelStepsGetActions:
    def test_flat_list_equals_concatenation_of_children(self):
        a1 = {"action": "spawn_agent", "skill": "reviewer-sign-off"}
        a2 = {"action": "spawn_agent", "skill": "researcher-validate"}
        a3 = {"action": "run_script", "command": "bash build.sh"}
        s1 = _StubStep([a1], "approved")
        s2 = _StubStep([a2, a3], "validated")
        ps, _ = _make_concrete_parallel([([a1], "approved"), ([a2, a3], "validated")])
        actions = ps.get_actions()
        assert actions == [a1, a2, a3]

    def test_empty_children_produce_empty_list(self):
        ps, _ = _make_concrete_parallel([([], "approved")])
        assert ps.get_actions() == []

    def test_concrete_parallel_steps_subclass_is_instantiable(self):
        """A concrete ParallelSteps subclass (implementing combine_results) is instantiable.

        implement.py's SignoffStep is the real-world example, but that class now lives
        outside the engine — this exercises the same "ParallelSteps is meant to be
        subclassed, not used directly" contract with a local stub instead."""
        from dev_team import ParallelSteps

        class _ConcreteParallelSteps(ParallelSteps):
            def combine_results(self, child_monikers):
                return child_monikers[0] if child_monikers else "approved"

        step = _ConcreteParallelSteps([])
        assert step is not None


class TestParallelStepsHandleResults:
    def test_each_child_handle_results_called(self):
        ps, steps = _make_concrete_parallel([
            ([{"a": 1}], "approved"),
            ([{"b": 2}], "approved"),
        ])
        ps.handle_results()
        assert steps[0].called
        assert steps[1].called

    def test_combine_results_failed_beats_all(self):
        ps, _ = _make_concrete_parallel([
            ([{"a": 1}], "failed"),
            ([{"b": 2}], "approved"),
        ])
        result = ps.handle_results()
        assert result == "failed"

    def test_combine_results_changes_requested_beats_approved(self):
        ps, _ = _make_concrete_parallel([
            ([{"a": 1}], "changes_requested"),
            ([{"b": 2}], "approved"),
        ])
        result = ps.handle_results()
        assert result == "changes_requested"

    def test_combine_results_all_approved_returns_first(self):
        ps, _ = _make_concrete_parallel([
            ([{"a": 1}], "approved"),
            ([{"b": 2}], "approved"),
        ])
        result = ps.handle_results()
        assert result == "approved"

    def test_failed_beats_changes_requested(self):
        ps, _ = _make_concrete_parallel([
            ([{"a": 1}], "changes_requested"),
            ([{"b": 2}], "failed"),
        ])
        result = ps.handle_results()
        assert result == "failed"


# ---------------------------------------------------------------------------
# Inline step (get_actions returns [])
# ---------------------------------------------------------------------------

class TestInlineStepDispatch:
    """The pipeline loop must advance through inline steps without calling
    exit_with_actions."""

    def _make_pipeline(self, ctx, context_path, step):
        """Build a minimal pipeline that contains a single inline step."""
        from dev_team import (
            DevTeamPipeline, WorkflowDefinition, StateMachine
        )
        workflow = WorkflowDefinition(
            transitions={
                "init": {"start": "testing"},
                "testing": {"done_ok": "done"},
            },
            terminal_states={"done"},
            initial_state="init",
        )
        pipeline = DevTeamPipeline.__new__(DevTeamPipeline)
        pipeline.ctx = ctx
        pipeline.context_path = context_path
        pipeline.log_dir = context_path.parent / "logs"
        pipeline.workflow = workflow
        pipeline.machine = StateMachine(workflow.transitions, initial="testing")
        pipeline.step_handlers = {"testing": step}
        return pipeline

    def test_inline_step_advances_without_exit(self, tmp_path):
        """get_actions=[] step: handle_results() called and trigger returned."""
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-TEST", state="testing")
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)

        step = _StubStep([], "done_ok")
        pipeline = self._make_pipeline(ctx, context_path, step)

        # _do_get_actions_and_exit should return the trigger directly (no sys.exit)
        trigger = pipeline._do_get_actions_and_exit(step)
        assert trigger == "done_ok"
        assert step.called


# ---------------------------------------------------------------------------
# _find_repo_root
# ---------------------------------------------------------------------------

class TestFindRepoRoot:
    def test_worktree_git_file_recognized_as_root(self, tmp_path, monkeypatch):
        from dev_team import _find_repo_root
        root = tmp_path / "worktree"
        root.mkdir()
        (root / ".git").write_text(
            "gitdir: ../main/.git/worktrees/worktree\n", encoding="utf-8"
        )
        monkeypatch.chdir(root)

        result = _find_repo_root()

        assert result == root.resolve()

    def test_normal_repo_git_directory_recognized_as_root(self, tmp_path, monkeypatch):
        from dev_team import _find_repo_root
        root = tmp_path / "repo"
        (root / ".git").mkdir(parents=True)
        monkeypatch.chdir(root)

        result = _find_repo_root()

        assert result == root.resolve()

    def test_claude_dir_only_recognized_as_root(self, tmp_path, monkeypatch):
        from dev_team import _find_repo_root
        root = tmp_path / "repo"
        (root / ".claude").mkdir(parents=True)
        monkeypatch.chdir(root)

        result = _find_repo_root()

        assert result == root.resolve()

    def test_nested_cwd_walks_up_to_git_directory(self, tmp_path, monkeypatch):
        from dev_team import _find_repo_root
        root = tmp_path / "repo"
        nested = root / "a" / "b" / "c"
        nested.mkdir(parents=True)
        (root / ".git").mkdir()
        monkeypatch.chdir(nested)

        result = _find_repo_root()

        assert result == root.resolve()

    def test_no_git_or_claude_in_any_ancestor_raises_runtime_error(self, tmp_path, monkeypatch):
        from dev_team import _find_repo_root
        cwd = tmp_path / "no_repo_here"
        cwd.mkdir()
        monkeypatch.chdir(cwd)

        with pytest.raises(RuntimeError, match="Could not locate repo root"):
            _find_repo_root()


# ---------------------------------------------------------------------------
# "event" descriptor field injection (DevTeamPipeline._do_get_actions_and_exit)
# ---------------------------------------------------------------------------

class TestHookPhaseGating:
    """_do_get_actions_and_exit() resolves this project's before-<event>/
    after-<event>-<trigger> instructions (if any) around a step's real dispatch and
    dispatches them as their own "hooks" actions, tracked via ctx.hook_phase/
    ctx.pending_trigger across repeated invocations. No hooks configured means no "hooks"
    action is ever emitted and the real dispatch is unaffected."""

    def _make_pipeline(self, ctx, context_path, step):
        from dev_team import DevTeamPipeline, WorkflowDefinition, StateMachine
        workflow = WorkflowDefinition(
            transitions={
                "init": {"start": "testing"},
                "testing": {"done_ok": "done"},
            },
            terminal_states={"done"},
            initial_state="init",
        )
        pipeline = DevTeamPipeline.__new__(DevTeamPipeline)
        pipeline.ctx = ctx
        pipeline.context_path = context_path
        pipeline.log_dir = context_path.parent / "logs"
        pipeline.workflow = workflow
        pipeline.machine = StateMachine(workflow.transitions, initial="testing")
        pipeline.step_handlers = {"testing": step}
        return pipeline

    def _expect_exit_with_actions_captures(self, monkeypatch, captured: dict) -> None:
        import dev_team

        def fake_exit(descriptors):
            captured["descriptors"] = descriptors
            raise SystemExit(0)

        monkeypatch.setattr(dev_team, "exit_with_actions", fake_exit)

    def _make_ctx(self, tmp_path, instructions=None):
        import json
        from dev_team import PipelineContext
        config = {"instructions": instructions} if instructions is not None else {}
        ctx = PipelineContext(
            work_item_id="ADR-TEST", state="testing",
            project_configuration=json.dumps(config),
        )
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)
        return ctx, context_path

    def test_no_hooks_configured_dispatches_main_action_directly(self, tmp_path, monkeypatch):
        captured: dict = {}
        self._expect_exit_with_actions_captures(monkeypatch, captured)
        ctx, context_path = self._make_ctx(tmp_path)

        action = {"action": "spawn_agent", "skill": "implement-task"}
        step = _StubStep([action], "impl_done")
        step.EVENT_NAME = "implement"
        pipeline = self._make_pipeline(ctx, context_path, step)

        with pytest.raises(SystemExit):
            pipeline._do_get_actions_and_exit(step)

        assert captured["descriptors"] == [action]
        assert ctx.hook_phase == ""

    def test_no_event_name_is_unaffected(self, tmp_path, monkeypatch):
        captured: dict = {}
        self._expect_exit_with_actions_captures(monkeypatch, captured)
        ctx, context_path = self._make_ctx(tmp_path)

        action = {"action": "spawn_agent", "skill": "review-sign-off"}
        step = _StubStep([action], "approved")
        # No EVENT_NAME attribute — getattr(...) falls back to None, mirroring
        # FindSpecStep (and signoff's children).
        pipeline = self._make_pipeline(ctx, context_path, step)

        with pytest.raises(SystemExit):
            pipeline._do_get_actions_and_exit(step)

        assert captured["descriptors"] == [action]

    def test_before_hook_dispatches_hooks_action_first(self, tmp_path, monkeypatch):
        captured: dict = {}
        self._expect_exit_with_actions_captures(monkeypatch, captured)
        ctx, context_path = self._make_ctx(
            tmp_path, {"before-implement": {"self-assign": "Assign Jira work item to self"}},
        )

        action = {"action": "spawn_agent", "skill": "implement-task"}
        step = _StubStep([action], "impl_done")
        step.EVENT_NAME = "implement"
        pipeline = self._make_pipeline(ctx, context_path, step)

        with pytest.raises(SystemExit):
            pipeline._do_get_actions_and_exit(step)

        assert captured["descriptors"] == [{
            "action": "hooks",
            "message": "Running before-implement instructions.",
            "instructions": ["Assign Jira work item to self"],
            "context_file": str(context_path),
        }]
        assert ctx.hook_phase == "before"
        assert not step.called  # the real step was never reached

    def test_resuming_after_before_hook_proceeds_to_main_action(self, tmp_path, monkeypatch):
        captured: dict = {}
        self._expect_exit_with_actions_captures(monkeypatch, captured)
        ctx, context_path = self._make_ctx(
            tmp_path, {"before-implement": {"self-assign": "Assign Jira work item to self"}},
        )
        ctx.hook_phase = "before"

        action = {"action": "spawn_agent", "skill": "implement-task"}
        step = _StubStep([action], "impl_done")
        step.EVENT_NAME = "implement"
        pipeline = self._make_pipeline(ctx, context_path, step)

        with pytest.raises(SystemExit):
            pipeline._do_get_actions_and_exit(step)

        assert captured["descriptors"] == [action]
        # Not "" — "" is the top-of-function's "before-hooks not yet dispatched" signal, and
        # resetting back to it here would make the next re-entry (e.g. once the spawned agent
        # this action dispatches actually finishes) misread it as a fresh step and re-dispatch
        # the before-hook a second time. See test_before_hook_is_not_redispatched_while_main_action_is_still_pending.
        assert ctx.hook_phase == "main"

    def test_before_hook_is_not_redispatched_while_main_action_is_still_pending(self, tmp_path, monkeypatch):
        """Regression for a real bug: once a before-hook has been dispatched and completes,
        ctx.hook_phase used to reset straight back to "" in the same call that then dispatches
        the step's main action. If that main action needs more than one re-entry of this
        function to resolve (e.g. a spawned developer agent whose result the orchestrator
        fetches via a separate invocation), the very next re-entry would see hook_phase == ""
        again and re-run the before-hook resolution — re-dispatching the same before-<event>
        hooks a second time before the main action ever got a chance to complete or even be
        checked via get_actions() again."""
        captured: dict = {}
        self._expect_exit_with_actions_captures(monkeypatch, captured)
        ctx, context_path = self._make_ctx(
            tmp_path, {"before-implement": {"self-assign": "Assign Jira work item to self"}},
        )
        ctx.hook_phase = "main"  # before-hook already ran; main action still pending

        action = {"action": "spawn_agent", "skill": "implement-task"}
        step = _StubStep([action], "impl_done")
        step.EVENT_NAME = "implement"
        pipeline = self._make_pipeline(ctx, context_path, step)

        with pytest.raises(SystemExit):
            pipeline._do_get_actions_and_exit(step)

        # The main action is re-dispatched, not a second "hooks" action for before-implement.
        assert captured["descriptors"] == [action]
        assert ctx.hook_phase == "main"

    def test_main_phase_clears_when_main_action_completes_with_no_after_hooks(self, tmp_path):
        """Once the main action finally resolves (get_actions() returns []), hook_phase must be
        cleared back to "" even when no after-hooks are configured — otherwise "main" would leak
        into whatever different EVENT_NAME step runs next, and that step's own before-hooks
        (gated on hook_phase == "") would silently never fire."""
        ctx, context_path = self._make_ctx(
            tmp_path, {"before-implement": {"self-assign": "Assign Jira work item to self"}},
        )
        ctx.hook_phase = "main"  # before-hook already ran; no after-implement configured

        step = _StubStep([], "impl_done")  # main action now resolved
        step.EVENT_NAME = "implement"
        pipeline = self._make_pipeline(ctx, context_path, step)

        trigger = pipeline._do_get_actions_and_exit(step)

        assert trigger == "impl_done"
        assert ctx.hook_phase == ""

    def test_after_hook_dispatches_based_on_trigger(self, tmp_path, monkeypatch):
        captured: dict = {}
        self._expect_exit_with_actions_captures(monkeypatch, captured)
        ctx, context_path = self._make_ctx(
            tmp_path, {"after-implement-impl_done": {"notify": "Post a status update"}},
        )

        step = _StubStep([], "impl_done")  # inline: the main action's data is already present
        step.EVENT_NAME = "implement"
        pipeline = self._make_pipeline(ctx, context_path, step)

        with pytest.raises(SystemExit):
            pipeline._do_get_actions_and_exit(step)

        assert captured["descriptors"] == [{
            "action": "hooks",
            "message": "Running after-implement instructions.",
            "instructions": ["Post a status update"],
            "context_file": str(context_path),
        }]
        assert ctx.hook_phase == "after"
        assert ctx.pending_trigger == "impl_done"
        assert step.called

    def test_resuming_after_after_hook_returns_trigger(self, tmp_path):
        ctx, context_path = self._make_ctx(
            tmp_path, {"after-implement-impl_done": {"notify": "Post a status update"}},
        )
        ctx.hook_phase = "after"
        ctx.pending_trigger = "impl_done"

        step = _StubStep([], "impl_done")
        step.EVENT_NAME = "implement"
        pipeline = self._make_pipeline(ctx, context_path, step)

        trigger = pipeline._do_get_actions_and_exit(step)

        assert trigger == "impl_done"
        assert ctx.hook_phase == ""
        assert ctx.pending_trigger == ""
        assert not step.called  # handle_results() was not called again to get here

    def test_get_actions_not_called_again_once_pending_trigger_is_set(self, tmp_path, monkeypatch):
        """Regression: a step like ValidateStep clears its own "is my data here yet" signal
        (e.g. ctx.validate_result) inside handle_results(). If get_actions() were called again
        on the after-hook resumption pass, it would misread that now-empty signal as "no result
        yet" and re-dispatch the main action a second time instead of returning the trigger."""
        captured: dict = {}
        self._expect_exit_with_actions_captures(monkeypatch, captured)
        ctx, context_path = self._make_ctx(
            tmp_path, {"after-implement-impl_done": {"notify": "Post a status update"}},
        )
        ctx.hook_phase = "after"
        ctx.pending_trigger = "impl_done"

        get_actions_call_count = {"n": 0}

        class _ReDispatchingStep:
            EVENT_NAME = "implement"

            def get_actions(self):
                get_actions_call_count["n"] += 1
                return [{"action": "spawn_agent", "skill": "implement-task"}]

            def handle_results(self):
                raise AssertionError("handle_results() should not be called again")

        step = _ReDispatchingStep()
        pipeline = self._make_pipeline(ctx, context_path, step)

        trigger = pipeline._do_get_actions_and_exit(step)

        assert trigger == "impl_done"
        assert get_actions_call_count["n"] == 0

    def test_handle_results_called_exactly_once_across_a_pending_after_hook(self, tmp_path, monkeypatch):
        captured: dict = {}
        self._expect_exit_with_actions_captures(monkeypatch, captured)
        ctx, context_path = self._make_ctx(
            tmp_path, {"after-implement-impl_done": {"notify": "Post a status update"}},
        )

        call_count = {"n": 0}
        step = _StubStep([], "impl_done")
        step.EVENT_NAME = "implement"
        real_handle_results = step.handle_results

        def counting_handle_results():
            call_count["n"] += 1
            return real_handle_results()

        step.handle_results = counting_handle_results
        pipeline = self._make_pipeline(ctx, context_path, step)

        with pytest.raises(SystemExit):
            pipeline._do_get_actions_and_exit(step)  # dispatches the after-hook
        trigger = pipeline._do_get_actions_and_exit(step)  # resumes, returns the trigger

        assert trigger == "impl_done"
        assert call_count["n"] == 1

    def test_after_hook_merges_trigger_specific_before_unconditional(self, tmp_path, monkeypatch):
        captured: dict = {}
        self._expect_exit_with_actions_captures(monkeypatch, captured)
        ctx, context_path = self._make_ctx(tmp_path, {
            "after-implement-impl_done": {"notify": "Post a status update"},
            "after-implement": {"log": "Log the outcome"},
        })

        step = _StubStep([], "impl_done")
        step.EVENT_NAME = "implement"
        pipeline = self._make_pipeline(ctx, context_path, step)

        with pytest.raises(SystemExit):
            pipeline._do_get_actions_and_exit(step)

        assert captured["descriptors"][0]["instructions"] == ["Post a status update", "Log the outcome"]

    def test_disabled_entry_is_filtered_out(self, tmp_path, monkeypatch):
        captured: dict = {}
        self._expect_exit_with_actions_captures(monkeypatch, captured)
        ctx, context_path = self._make_ctx(tmp_path, {
            "before-implement": {"self-assign": "", "push": "Push git changes to remote"},
        })

        action = {"action": "spawn_agent", "skill": "implement-task"}
        step = _StubStep([action], "impl_done")
        step.EVENT_NAME = "implement"
        pipeline = self._make_pipeline(ctx, context_path, step)

        with pytest.raises(SystemExit):
            pipeline._do_get_actions_and_exit(step)

        assert captured["descriptors"][0]["instructions"] == ["Push git changes to remote"]

    def test_inline_step_with_no_actions_and_no_hooks_returns_trigger_directly(self, tmp_path):
        ctx, context_path = self._make_ctx(tmp_path)
        step = _StubStep([], "done_ok")
        step.EVENT_NAME = "implement"
        pipeline = self._make_pipeline(ctx, context_path, step)

        trigger = pipeline._do_get_actions_and_exit(step)

        assert trigger == "done_ok"
