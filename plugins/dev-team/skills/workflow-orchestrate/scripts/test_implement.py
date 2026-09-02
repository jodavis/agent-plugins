"""Tests for implement.py — the implement/fix task-pipeline steps built on dev_team.py's
generic engine.

Covers:
- Counter increment/reset logic — signoff_cycle_count, review_cycle_count
- _parse_approval_status() / _researcher_validated() — agent-output parsing helpers
- signoff_build_result field — save/load round-trip
- _get_failing_pr_checks() / _resolve_validation_script() — shell-out helpers
- ValidateStep / BuildValidationStep / CreatePrStep / AddToPrStackStep / PlanStep /
  ResearchStep — concrete Step behavior (get_actions()/handle_results())
- EVENT_NAME declared per Step subclass
- Workflow asset routing (reviewing --> signoff --> add_to_pr_stack --> done)
- --print-context-path CLI flag on implement.py
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# --print-context-path CLI flag (implement.py)
# ---------------------------------------------------------------------------

class TestPrintContextPath:
    def test_prints_path_and_exits_zero(self, tmp_path, monkeypatch):
        """--print-context-path should print the path to stdout and exit 0."""
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "implement.py"),
             "ADR-123", "--print-context-path", "myorg/myrepo"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        expected = str(tmp_path / "myorg" / "myrepo" / "ADR-123.md")
        assert result.stdout.strip() == expected

    def test_uses_state_dir_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "implement.py"),
             "Issue-99", "--print-context-path", "org/repo"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        assert "Issue-99.md" in result.stdout

    def test_nothing_on_stderr(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "implement.py"),
             "ADR-1", "--print-context-path", "a/b"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# signoff_cycle_count counter
# ---------------------------------------------------------------------------

class TestSignoffCycleCount:
    def make_sut(self, **kwargs):
        from dev_team import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_starts_at_zero(self):
        ctx = self.make_sut()
        assert ctx.signoff_cycle_count == 0

    def test_increments_on_signoff_changes_requested(self):
        from implement import _apply_counter_updates
        ctx = self.make_sut()
        _apply_counter_updates(ctx, "signoff", "changes_requested")
        assert ctx.signoff_cycle_count == 1

    def test_accumulates_across_multiple_cycles(self):
        from implement import _apply_counter_updates
        ctx = self.make_sut()
        _apply_counter_updates(ctx, "signoff", "changes_requested")
        _apply_counter_updates(ctx, "signoff", "changes_requested")
        assert ctx.signoff_cycle_count == 2

    def test_resets_to_zero_on_signoff_approved(self):
        from implement import _apply_counter_updates
        ctx = self.make_sut(signoff_cycle_count=3)
        _apply_counter_updates(ctx, "signoff", "approved")
        assert ctx.signoff_cycle_count == 0

    def test_not_affected_by_reviewing_step(self):
        from implement import _apply_counter_updates
        ctx = self.make_sut(signoff_cycle_count=1)
        _apply_counter_updates(ctx, "reviewing", "changes_requested")
        assert ctx.signoff_cycle_count == 1

    def test_roundtrip_through_save_load(self, tmp_path):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-123", signoff_cycle_count=2)
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.signoff_cycle_count == 2


# ---------------------------------------------------------------------------
# review_cycle_count counter
# ---------------------------------------------------------------------------

class TestReviewCycleCount:
    def make_sut(self, **kwargs):
        from dev_team import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_starts_at_zero(self):
        ctx = self.make_sut()
        assert ctx.review_cycle_count == 0

    def test_increments_on_reviewing_step_changes_requested(self):
        from implement import _apply_counter_updates
        ctx = self.make_sut()
        _apply_counter_updates(ctx, "reviewing", "changes_requested")
        assert ctx.review_cycle_count == 1

    def test_increments_on_reviewing_step_approved(self):
        from implement import _apply_counter_updates
        ctx = self.make_sut()
        _apply_counter_updates(ctx, "reviewing", "approved")
        assert ctx.review_cycle_count == 1

    def test_resets_to_zero_on_signoff_approved(self):
        from implement import _apply_counter_updates
        ctx = self.make_sut(review_cycle_count=3)
        _apply_counter_updates(ctx, "signoff", "approved")
        assert ctx.review_cycle_count == 0

    def test_not_affected_by_signoff_changes_requested(self):
        from implement import _apply_counter_updates
        ctx = self.make_sut(review_cycle_count=1)
        _apply_counter_updates(ctx, "signoff", "changes_requested")
        assert ctx.review_cycle_count == 1

    def test_roundtrip_through_save_load(self, tmp_path):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-123", review_cycle_count=3)
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.review_cycle_count == 3


# ---------------------------------------------------------------------------
# _parse_approval_status
# ---------------------------------------------------------------------------

class TestParseApprovalStatus:
    def test_approved_json_returns_approved(self):
        from implement import _parse_approval_status
        assert _parse_approval_status('{"status": "approved"}') == "approved"

    def test_changes_requested_json_returns_changes_requested(self):
        from implement import _parse_approval_status
        assert _parse_approval_status('{"status": "changes_requested"}') == "changes_requested"

    def test_bare_approved_word_returns_approved(self):
        from implement import _parse_approval_status
        # Secondary heuristic when JSON parsing fails: "approved" keyword present
        assert _parse_approval_status("LGTM. Status: approved.") == "approved"

    def test_both_words_present_returns_changes_requested(self):
        from implement import _parse_approval_status
        # If both keywords appear, don't false-positive as approved
        content = "Previously approved but now changes_requested."
        assert _parse_approval_status(content) == "changes_requested"

    def test_unrecognised_content_defaults_to_changes_requested(self):
        from implement import _parse_approval_status
        assert _parse_approval_status("some random output") == "changes_requested"

    def test_json_with_pr_url_approved(self):
        from implement import _parse_approval_status
        content = '{"status": "approved", "pr_url": "https://github.com/org/repo/pull/1"}'
        assert _parse_approval_status(content) == "approved"


# ---------------------------------------------------------------------------
# _researcher_validated
# ---------------------------------------------------------------------------

class TestResearcherValidated:
    def test_validated_json_object_returns_true(self):
        from implement import _researcher_validated
        assert _researcher_validated('{"status": "validated"}') is True

    def test_failed_json_object_returns_false(self):
        from implement import _researcher_validated
        assert _researcher_validated('{"status": "failed"}') is False

    def test_validated_with_criteria_array_returns_true(self):
        from implement import _researcher_validated
        content = '{"status": "validated", "criteria": [{"criterion": "Tests pass", "status": "pass"}]}'
        assert _researcher_validated(content) is True

    def test_failed_with_criteria_array_returns_false(self):
        from implement import _researcher_validated
        content = '{"status": "failed", "criteria": [{"criterion": "Tests pass", "status": "fail", "finding": "not met"}]}'
        assert _researcher_validated(content) is False

    def test_validated_embedded_in_prose_returns_true(self):
        from implement import _researcher_validated
        # JSON on its own line within agent prose output
        content = 'All criteria were met.\n{"status": "validated", "criteria": []}'
        assert _researcher_validated(content) is True

    def test_failed_embedded_in_prose_returns_false(self):
        from implement import _researcher_validated
        content = 'Some criteria were not met.\n{"status": "failed", "criteria": []}'
        assert _researcher_validated(content) is False

    def test_unrecognised_content_returns_false(self):
        from implement import _researcher_validated
        assert _researcher_validated("some unexpected output") is False

    def test_empty_string_returns_false(self):
        from implement import _researcher_validated
        assert _researcher_validated("") is False


# ---------------------------------------------------------------------------
# signoff_build_result field
# ---------------------------------------------------------------------------

class TestSignoffBuildResult:
    def make_sut(self, **kwargs):
        from dev_team import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_defaults_to_empty_string(self):
        ctx = self.make_sut()
        assert ctx.signoff_build_result == ""

    def test_roundtrip_through_save_load(self, tmp_path):
        from dev_team import PipelineContext
        # script-runner returns "passed — log: <path>", not bare "passed"
        result = "passed — log: /home/user/.dev-team/ADR-123/logs/ADR-123-signoff-20240101T120000.log"
        ctx = PipelineContext(work_item_id="ADR-123", signoff_build_result=result)
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.signoff_build_result == result

    def test_failed_result_roundtrip(self, tmp_path):
        from dev_team import PipelineContext
        result = "failed — log: /home/user/.dev-team/ADR-123/logs/ADR-123-signoff-20240101T120000.log"
        ctx = PipelineContext(work_item_id="ADR-123", signoff_build_result=result)
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.signoff_build_result == result

    def test_passed_with_log_path_is_recognized(self):
        """script-runner returns 'passed — log: <path>'; startswith check must succeed."""
        result = "passed — log: /home/user/.dev-team/ADR-123/logs/ADR-123-signoff-20240101T120000.log"
        assert result.strip().startswith("passed")

    def test_failed_with_log_path_is_not_passed(self):
        """script-runner returns 'failed — log: <path>'; must not satisfy the passed check."""
        result = "failed — log: /home/user/.dev-team/ADR-123/logs/ADR-123-signoff-20240101T120000.log"
        assert not result.strip().startswith("passed")

    def test_empty_string_roundtrip(self, tmp_path):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-123", signoff_build_result="")
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.signoff_build_result == ""

    def test_reset_alongside_signoff_sections(self):
        """signoff_build_result can be reset to empty alongside signoff_review/research."""
        ctx = self.make_sut(
            signoff_review="approved",
            signoff_research="validated",
            signoff_build_result="passed — log: /tmp/test.log",
        )
        ctx.signoff_review = ""
        ctx.signoff_research = ""
        ctx.signoff_build_result = ""
        assert ctx.signoff_build_result == ""
        assert ctx.signoff_review == ""
        assert ctx.signoff_research == ""


# ---------------------------------------------------------------------------
# ReviewStep pr_url extraction from "PR URL" section
# ---------------------------------------------------------------------------

class TestReviewStepPrUrlExtraction:
    def make_sut(self, **kwargs):
        from dev_team import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_pr_url_saved_to_frontmatter_after_extraction(self, tmp_path):
        """When pending_agent==create-pr and PR URL section is written, pr_url lands in frontmatter."""
        from dev_team import PipelineContext
        ctx = self.make_sut(
            state="creating_pr",
            pending_agent="create-pr",
            work_summaries=["# Summary"],
        )
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)

        # Simulate task-runner writing the PR URL section
        text = context_path.read_text(encoding="utf-8")
        text += "\n<!-- section:PR URL -->\n\nhttps://github.com/org/repo/pull/42\n"
        context_path.write_text(text, encoding="utf-8")

        # load() should NOT pick up pr_url from section (fallback removed)
        loaded = PipelineContext.load(context_path)
        assert loaded.pr_url == ""

    def test_load_does_not_fallback_to_pr_url_section(self, tmp_path):
        """After removing the fallback, pr_url from section is NOT loaded automatically."""
        from dev_team import PipelineContext
        ctx = self.make_sut()
        path = tmp_path / "ctx.md"
        ctx.save(path)
        text = path.read_text(encoding="utf-8")
        text += "\n<!-- section:PR URL -->\n\nhttps://github.com/org/repo/pull/99\n"
        path.write_text(text, encoding="utf-8")
        loaded = PipelineContext.load(path)
        # Section fallback removed — pr_url should be empty
        assert loaded.pr_url == ""

    def test_pr_url_in_frontmatter_is_loaded(self, tmp_path):
        """pr_url set explicitly in frontmatter IS loaded correctly."""
        from dev_team import PipelineContext
        ctx = self.make_sut(pr_url="https://github.com/org/repo/pull/7")
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.pr_url == "https://github.com/org/repo/pull/7"


# ---------------------------------------------------------------------------
# _get_failing_pr_checks
# ---------------------------------------------------------------------------

class TestGetFailingPrChecks:
    def test_returns_empty_when_gh_not_found(self, monkeypatch):
        """Returns empty string when gh CLI is not available."""
        from unittest.mock import patch
        from implement import _get_failing_pr_checks
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _get_failing_pr_checks("https://github.com/org/repo/pull/1")
        assert result == ""

    def test_returns_empty_on_timeout(self):
        from unittest.mock import patch
        import subprocess as sp
        from implement import _get_failing_pr_checks
        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="gh", timeout=60)):
            result = _get_failing_pr_checks("https://github.com/org/repo/pull/1")
        assert result == ""

    def test_returns_failing_lines_when_present(self):
        from unittest.mock import patch, MagicMock
        from implement import _get_failing_pr_checks
        mock_result = MagicMock()
        mock_result.stdout = "build\tpass\nbuild-test\tfail\nlint\tpass\n"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            result = _get_failing_pr_checks("https://github.com/org/repo/pull/1")
        assert "fail" in result
        assert "pass" not in result or "fail" in result

    def test_returns_empty_when_all_pass(self):
        from unittest.mock import patch, MagicMock
        from implement import _get_failing_pr_checks
        mock_result = MagicMock()
        mock_result.stdout = "build\tpass\nlint\tpass\n"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            result = _get_failing_pr_checks("https://github.com/org/repo/pull/1")
        assert result == ""


# ---------------------------------------------------------------------------
# _resolve_validation_script / ValidateStep configurability
# ---------------------------------------------------------------------------

class TestResolveValidationScript:
    def test_validation_list_resolves_to_run_validation_command(self, tmp_path):
        from implement import _resolve_validation_script
        config = {"validation": ["scripts/validate.sh"]}
        result = _resolve_validation_script(config, tmp_path)
        assert "run_validation.py" in result
        assert f'--repo-root "{tmp_path}"' in result

    def test_validation_multi_command_list_still_resolves_to_run_validation_command(self, tmp_path):
        from implement import _resolve_validation_script
        config = {"validation": ["npm run build", "npm test"]}
        result = _resolve_validation_script(config, tmp_path)
        assert "run_validation.py" in result
        assert f'--repo-root "{tmp_path}"' in result

    def test_validation_null_returns_none(self, tmp_path):
        from implement import _resolve_validation_script
        config = {"validation": None}
        assert _resolve_validation_script(config, tmp_path) is None

    def test_validation_empty_list_returns_none(self, tmp_path):
        from implement import _resolve_validation_script
        config = {"validation": []}
        assert _resolve_validation_script(config, tmp_path) is None

    def test_validation_key_absent_returns_none(self, tmp_path):
        from implement import _resolve_validation_script
        assert _resolve_validation_script({}, tmp_path) is None

    def test_validation_list_resolves_to_sys_executable_command(self, tmp_path):
        """Must invoke the current interpreter (sys.executable), never a bare `python`,
        since not every environment has a `python` command on PATH (only `python3`)."""
        from implement import _resolve_validation_script
        config = {"validation": ["scripts/validate.sh"]}
        result = _resolve_validation_script(config, tmp_path)
        assert result.startswith(f'{sys.executable} ')


class TestValidateStepGetActions:
    def _make_ctx(self, tmp_path, **kwargs):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-TEST", **kwargs)
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)
        return ctx, context_path

    def test_skips_run_script_when_no_validation_script_configured(self, tmp_path, monkeypatch):
        """A repo that opts out of validation (validation: null) should not spawn a script run."""
        from implement import ValidateStep

        ctx, context_path = self._make_ctx(
            tmp_path, project_configuration=json.dumps({"validation": None}),
        )
        step = ValidateStep(ctx, context_path, tmp_path / "logs")

        actions = step.get_actions()

        assert actions == []
        assert ctx.validate_result.startswith("Succeeded")

    def test_returns_run_script_action_when_configured(self, tmp_path, monkeypatch):
        import implement
        from implement import ValidateStep, _resolve_validation_script

        monkeypatch.setattr(implement, "REPO_ROOT", tmp_path)
        config = {"validation": ["scripts/validate.sh"]}
        ctx, context_path = self._make_ctx(
            tmp_path, project_configuration=json.dumps(config),
        )
        step = ValidateStep(ctx, context_path, tmp_path / "logs")

        actions = step.get_actions()

        assert len(actions) == 1
        assert actions[0]["action"] == "run_script"
        assert actions[0]["command"] == _resolve_validation_script(config, tmp_path)

    def test_uses_cached_project_configuration_without_reloading(self, tmp_path, monkeypatch):
        import dev_team
        import implement
        from implement import ValidateStep, _resolve_validation_script

        def _fail(repo_root):
            raise AssertionError("_load_project_config should not be called when cached")

        monkeypatch.setattr(dev_team, "_load_project_config", _fail)
        monkeypatch.setattr(implement, "REPO_ROOT", tmp_path)
        config = {"validation": ["scripts/validate.sh"]}
        ctx, context_path = self._make_ctx(
            tmp_path, project_configuration=json.dumps(config),
        )
        step = ValidateStep(ctx, context_path, tmp_path / "logs")

        actions = step.get_actions()

        assert len(actions) == 1
        assert actions[0]["command"] == _resolve_validation_script(config, tmp_path)


class TestBuildValidationStepGetActions:
    def _make_ctx(self, tmp_path, **kwargs):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-TEST", **kwargs)
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)
        return ctx, context_path

    def test_run_script_command_uses_sys_executable(self, tmp_path):
        """Must invoke the current interpreter (sys.executable), never a bare `python`,
        since not every environment has a `python` command on PATH (only `python3`)."""
        from implement import BuildValidationStep

        ctx, context_path = self._make_ctx(tmp_path, pr_url="https://github.com/org/repo/pull/1")
        step = BuildValidationStep(ctx, context_path, tmp_path / "logs")

        actions = step.get_actions()

        assert len(actions) == 1
        assert actions[0]["command"].startswith(f'{sys.executable} ')


class TestValidateStepHandleResults:
    def _make_ctx(self, tmp_path, **kwargs):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-TEST", **kwargs)
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)
        return ctx, context_path

    def test_commits_and_pushes_when_no_validation_script_configured(self, tmp_path, monkeypatch):
        """No-script path resolves entirely inline — it has no hook mechanism, so the
        hardcoded push must still fire."""
        import implement
        from implement import ValidateStep
        from unittest.mock import MagicMock

        mock_commit_and_push = MagicMock(spec=implement._commit_and_push)
        monkeypatch.setattr(implement, "_commit_and_push", mock_commit_and_push)
        ctx, context_path = self._make_ctx(
            tmp_path,
            validate_result="Succeeded (no validation script configured for this project)",
        )
        step = ValidateStep(ctx, context_path, tmp_path / "logs")

        trigger = step.handle_results()

        assert trigger == "clean"
        mock_commit_and_push.assert_called_once_with("ADR-TEST")

    def test_skips_commit_and_push_when_validation_script_ran(self, tmp_path, monkeypatch):
        """A real validation script already pushed via workflow-script's own
        after-validate-success push hook — pushing again here would be redundant."""
        import implement
        from implement import ValidateStep
        from unittest.mock import MagicMock

        mock_commit_and_push = MagicMock(spec=implement._commit_and_push)
        monkeypatch.setattr(implement, "_commit_and_push", mock_commit_and_push)
        ctx, context_path = self._make_ctx(
            tmp_path,
            validate_result="Succeeded",
        )
        step = ValidateStep(ctx, context_path, tmp_path / "logs")

        trigger = step.handle_results()

        assert trigger == "clean"
        mock_commit_and_push.assert_not_called()


class TestValidateStepHandleResults:
    def _make_ctx(self, tmp_path, **kwargs):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-TEST", **kwargs)
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)
        return ctx, context_path

    def test_commits_and_pushes_when_no_validation_script_configured(self, tmp_path, monkeypatch):
        """No-script path resolves entirely inline — it has no hook mechanism, so the
        hardcoded push must still fire."""
        import implement
        from implement import ValidateStep
        from unittest.mock import MagicMock

        mock_commit_and_push = MagicMock(spec=implement._commit_and_push)
        monkeypatch.setattr(implement, "_commit_and_push", mock_commit_and_push)
        ctx, context_path = self._make_ctx(
            tmp_path,
            validate_result="Succeeded (no validation script configured for this project)",
        )
        step = ValidateStep(ctx, context_path, tmp_path / "logs")

        trigger = step.handle_results()

        assert trigger == "clean"
        mock_commit_and_push.assert_called_once_with("ADR-TEST")

    def test_skips_commit_and_push_when_validation_script_ran(self, tmp_path, monkeypatch):
        """A real validation script already pushed via workflow-script's own
        after-validate-success push hook — pushing again here would be redundant."""
        import implement
        from implement import ValidateStep
        from unittest.mock import MagicMock

        mock_commit_and_push = MagicMock(spec=implement._commit_and_push)
        monkeypatch.setattr(implement, "_commit_and_push", mock_commit_and_push)
        ctx, context_path = self._make_ctx(
            tmp_path,
            validate_result="Succeeded",
        )
        step = ValidateStep(ctx, context_path, tmp_path / "logs")

        trigger = step.handle_results()

        assert trigger == "clean"
        mock_commit_and_push.assert_not_called()


# ---------------------------------------------------------------------------
# CreatePrStep
# ---------------------------------------------------------------------------

class TestCreatePrStep:
    def _make_ctx(self, tmp_path, **kwargs):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-TEST", **kwargs)
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)
        return ctx, context_path

    def test_get_actions_returns_descriptor_when_no_pr_url(self, tmp_path):
        from implement import CreatePrStep
        ctx, context_path = self._make_ctx(tmp_path, work_summaries=["# Summary"])
        step = CreatePrStep(ctx, context_path)
        actions = step.get_actions()
        assert len(actions) == 1
        assert actions[0]["skill"] == "create-pr-from-context"

    def test_get_actions_returns_empty_when_pr_url_already_set(self, tmp_path):
        """Recovery re-entry: pr_url already in context — inline step."""
        from implement import CreatePrStep
        ctx, context_path = self._make_ctx(
            tmp_path,
            pr_url="https://github.com/org/repo/pull/5",
            work_summaries=["# Summary"],
        )
        step = CreatePrStep(ctx, context_path)
        assert step.get_actions() == []

    def test_handle_results_returns_pr_created_when_pr_url_already_set(self, tmp_path):
        """Inline path: pr_url was set before handle_results() — returns pr_created."""
        from implement import CreatePrStep
        ctx, context_path = self._make_ctx(
            tmp_path,
            pr_url="https://github.com/org/repo/pull/5",
        )
        step = CreatePrStep(ctx, context_path)
        trigger = step.handle_results()
        assert trigger == "pr_created"

    def test_handle_results_extracts_pr_url_from_section(self, tmp_path):
        """Normal dispatch: agent writes PR URL section; handle_results extracts it."""
        from implement import CreatePrStep
        ctx, context_path = self._make_ctx(tmp_path)
        # Simulate agent writing the PR URL section as JSON (standardized format)
        text = context_path.read_text(encoding="utf-8")
        text += '\n<!-- section:PR URL -->\n\n{"pr_url": "https://github.com/org/repo/pull/42"}\n'
        context_path.write_text(text, encoding="utf-8")

        step = CreatePrStep(ctx, context_path)
        trigger = step.handle_results()
        assert trigger == "pr_created"
        assert ctx.pr_url == "https://github.com/org/repo/pull/42"

    def test_handle_results_increments_failures_when_no_pr_url_written(self, tmp_path):
        """Failure path: agent ran but did not write PR URL."""
        from implement import CreatePrStep
        ctx, context_path = self._make_ctx(tmp_path)
        step = CreatePrStep(ctx, context_path)
        trigger = step.handle_results()
        # Still returns pr_created (fallback) but consecutive_failures incremented
        assert ctx.consecutive_failures == 1

    def test_descriptor_includes_required_fields(self, tmp_path):
        from implement import CreatePrStep
        ctx, context_path = self._make_ctx(tmp_path, work_summaries=["# Summary"])
        step = CreatePrStep(ctx, context_path)
        actions = step.get_actions()
        assert actions[0]["action"] == "spawn_agent"
        assert actions[0]["write_section"] == "PR URL"
        assert "context_file" in actions[0]


# ---------------------------------------------------------------------------
# AddToPrStackStep
# ---------------------------------------------------------------------------

class TestAddToPrStackStep:
    def _make_ctx(self, tmp_path, **kwargs):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-TEST", **kwargs)
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)
        return ctx, context_path

    def test_get_actions_returns_descriptor_when_not_added_to_stack(self, tmp_path):
        from implement import AddToPrStackStep
        ctx, context_path = self._make_ctx(tmp_path)
        step = AddToPrStackStep(ctx, context_path)
        actions = step.get_actions()
        assert len(actions) == 1
        assert actions[0]["skill"] == "add-to-pr-stack"

    def test_get_actions_returns_empty_when_already_added_to_stack(self, tmp_path):
        """Recovery re-entry: added_to_stack already true — inline step."""
        from implement import AddToPrStackStep
        ctx, context_path = self._make_ctx(tmp_path, added_to_stack=True)
        step = AddToPrStackStep(ctx, context_path)
        assert step.get_actions() == []

    def test_handle_results_returns_linked_when_already_added_to_stack(self, tmp_path):
        """Inline path: added_to_stack was set before handle_results() — returns linked."""
        from implement import AddToPrStackStep
        ctx, context_path = self._make_ctx(tmp_path, added_to_stack=True)
        step = AddToPrStackStep(ctx, context_path)
        trigger = step.handle_results()
        assert trigger == "linked"

    def test_get_actions_returns_empty_when_stack_link_status_already_resolved(self, tmp_path):
        """Recovery re-entry for a not-applicable task: added_to_stack never becomes true for
        it, so stack_link_status (an extra_frontmatter key add_to_pr_stack.py always writes on
        success) is what actually prevents re-spawning the agent forever."""
        from implement import AddToPrStackStep
        ctx, context_path = self._make_ctx(
            tmp_path, extra_frontmatter={"stack_link_status": "not_applicable"}
        )
        step = AddToPrStackStep(ctx, context_path)
        assert step.get_actions() == []

    def test_handle_results_returns_linked_when_stack_link_status_already_resolved(self, tmp_path):
        from implement import AddToPrStackStep
        ctx, context_path = self._make_ctx(
            tmp_path, extra_frontmatter={"stack_link_status": "not_applicable"}
        )
        step = AddToPrStackStep(ctx, context_path)
        trigger = step.handle_results()
        assert trigger == "linked"
        assert ctx.consecutive_failures == 0

    def test_handle_results_extracts_linked_status_from_section(self, tmp_path):
        """Normal dispatch: agent writes Stack Link Result section; handle_results extracts it."""
        from implement import AddToPrStackStep
        ctx, context_path = self._make_ctx(tmp_path)
        text = context_path.read_text(encoding="utf-8")
        text += '\n<!-- section:Stack Link Result -->\n\n{"status": "linked"}\n'
        context_path.write_text(text, encoding="utf-8")

        step = AddToPrStackStep(ctx, context_path)
        trigger = step.handle_results()
        assert trigger == "linked"
        assert ctx.consecutive_failures == 0

    def test_handle_results_treats_not_applicable_status_as_success(self, tmp_path):
        """A task with no epic (or no local spec) reports not_applicable, not linked — still a
        success, since there was genuinely nothing to register."""
        from implement import AddToPrStackStep
        ctx, context_path = self._make_ctx(tmp_path)
        text = context_path.read_text(encoding="utf-8")
        text += '\n<!-- section:Stack Link Result -->\n\n{"status": "not_applicable"}\n'
        context_path.write_text(text, encoding="utf-8")

        step = AddToPrStackStep(ctx, context_path)
        trigger = step.handle_results()
        assert trigger == "linked"
        assert ctx.consecutive_failures == 0

    def test_handle_results_increments_failures_when_no_result_written(self, tmp_path):
        """Failure path: agent ran but did not write a Stack Link Result section."""
        from implement import AddToPrStackStep
        ctx, context_path = self._make_ctx(tmp_path)
        step = AddToPrStackStep(ctx, context_path)
        trigger = step.handle_results()
        # Still returns linked (no dedicated retry edge, mirroring CreatePrStep's own
        # precedent), but consecutive_failures is incremented for troubleshooter escalation.
        assert trigger == "linked"
        assert ctx.consecutive_failures == 1

    def test_descriptor_includes_required_fields(self, tmp_path):
        from implement import AddToPrStackStep
        ctx, context_path = self._make_ctx(tmp_path)
        step = AddToPrStackStep(ctx, context_path)
        actions = step.get_actions()
        assert actions[0]["action"] == "spawn_agent"
        assert actions[0]["write_section"] == "Stack Link Result"
        assert "context_file" in actions[0]


# ---------------------------------------------------------------------------
# PlanStep / ResearchStep — /implement's `planning` state vs /fix's `researching` state
# ---------------------------------------------------------------------------

class TestPlanStep:
    """`/implement`'s planning state: hardcodes the Planner agent and plan-task skill."""

    def _make_ctx(self, tmp_path, **kwargs):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="ADR-TEST", **kwargs)
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)
        return ctx, context_path

    def test_get_actions_spawns_planner_agent_with_plan_task_skill(self, tmp_path):
        from implement import PlanStep
        ctx, context_path = self._make_ctx(tmp_path)
        step = PlanStep(ctx, context_path)
        actions = step.get_actions()
        assert len(actions) == 1
        assert actions[0]["agent"] == "dev-team:planner"
        assert actions[0]["skill"] == "plan-task"
        assert actions[0]["write_section"] == "Researcher Brief"

    def test_get_actions_returns_empty_when_brief_already_set(self, tmp_path):
        from implement import PlanStep
        ctx, context_path = self._make_ctx(tmp_path, brief="# Implementation plan")
        step = PlanStep(ctx, context_path)
        assert step.get_actions() == []

    def test_handle_results_returns_ready_when_brief_present(self, tmp_path):
        from implement import PlanStep
        ctx, context_path = self._make_ctx(tmp_path, brief="# Implementation plan")
        step = PlanStep(ctx, context_path)
        assert step.handle_results() == "ready"

    def test_handle_results_returns_ready_and_counts_failure_when_brief_missing(self, tmp_path):
        from implement import PlanStep
        ctx, context_path = self._make_ctx(tmp_path)
        step = PlanStep(ctx, context_path)
        trigger = step.handle_results()
        assert trigger == "ready"
        assert ctx.consecutive_failures == 1


class TestResearchStep:
    """`/fix`'s researching state: hardcodes the Researcher agent and researcher-issue skill."""

    def _make_ctx(self, tmp_path, **kwargs):
        from dev_team import PipelineContext
        ctx = PipelineContext(work_item_id="Issue-TEST", **kwargs)
        context_path = tmp_path / "ctx.md"
        ctx.save(context_path)
        return ctx, context_path

    def test_get_actions_spawns_researcher_agent_with_researcher_issue_skill(self, tmp_path):
        from implement import ResearchStep
        ctx, context_path = self._make_ctx(tmp_path)
        step = ResearchStep(ctx, context_path)
        actions = step.get_actions()
        assert len(actions) == 1
        assert actions[0]["agent"] == "dev-team:researcher"
        assert actions[0]["skill"] == "researcher-issue"
        assert actions[0]["write_section"] == "Researcher Brief"

    def test_handle_results_returns_research_done_when_brief_present(self, tmp_path):
        from implement import ResearchStep
        ctx, context_path = self._make_ctx(tmp_path, brief="# Root-cause plan")
        step = ResearchStep(ctx, context_path)
        assert step.handle_results() == "research_done"


# ---------------------------------------------------------------------------
# EVENT_NAME per Step
# ---------------------------------------------------------------------------

class TestEventNamePerStep:
    """Every single-action Step declares a stable EVENT_NAME; spec-finding (and signoff's
    own children) don't. `SignoffStep` itself carries EVENT_NAME = "signoff" directly —
    there is no separate hand-off step to carry it instead."""

    @pytest.mark.parametrize("step_class_name,expected_event", [
        ("DebugStep", "debug"),
        ("ResearchStep", "research"),
        ("PlanStep", "plan"),
        ("ImplementStep", "implement"),
        ("ValidateStep", "validate"),
        ("CreatePrStep", "create-pr"),
        ("ReviewStep", "review"),
        ("FixStep", "fix"),
        ("FixPrStep", "fix"),
        ("SignoffStep", "signoff"),
        ("AddToPrStackStep", "add-to-pr-stack"),
    ])
    def test_step_declares_expected_event_name(self, step_class_name, expected_event):
        import implement
        step_class = getattr(implement, step_class_name)
        assert step_class.EVENT_NAME == expected_event

    def test_find_spec_step_has_no_event_name(self):
        from implement import FindSpecStep
        assert FindSpecStep.EVENT_NAME is None

    @pytest.mark.parametrize("step_class_name", [
        "ReviewerSignOffStep", "BuildValidationStep",
    ])
    def test_signoff_child_step_has_no_event_name(self, step_class_name):
        """SignoffStep's children still dispatch via workflow-worker/workflow-script exactly
        as today, with no hooks of their own — hooks apply to signoff as a whole, resolved
        around SignoffStep's own resolution, not to these children individually."""
        import implement
        step_class = getattr(implement, step_class_name)
        assert step_class.EVENT_NAME is None

    def test_base_step_default_is_none(self):
        from dev_team import Step
        assert Step.EVENT_NAME is None


# ---------------------------------------------------------------------------
# Workflow asset transitions — reviewing must always route through signoff
# ---------------------------------------------------------------------------

class TestWorkflowAssetSignoffRouting:
    """Regression coverage for a real bug PR #99's human reviewer found: both shipped
    workflow assets let `reviewing --> handoff : approved` bypass `signoff` entirely on a
    clean first-pass review, so a task that never needed a `fixing_pr` cycle skipped the
    signoff parallel checks (and, before this fix, the hand-off hooks tied to them) outright.
    `reviewing`'s only `approved` exit must be `signoff` — `signoff` is what may reach
    `add_to_pr_stack`, never `reviewing` directly. `handoff` no longer exists as its own state
    (the `signoff` pipeline event now hangs directly off `SignoffStep`'s own resolution), and
    `add_to_pr_stack` (registering the signed-off PR into its epic's `gh stack`) is now the only
    state that reaches `done` — `signoff` itself no longer does, so the invariant is now "only
    `add_to_pr_stack` reaches `done`, and only `signoff` reaches `add_to_pr_stack`"."""

    ASSETS_DIR = SCRIPTS_DIR.parent / "assets"

    @pytest.mark.parametrize("asset_name", [
        "implement-task-plan.md",
        "fix-issue-plan.md",
    ])
    def test_reviewing_approved_routes_to_signoff_not_done(self, asset_name):
        from dev_team import parse_workflow
        workflow = parse_workflow(self.ASSETS_DIR / asset_name)
        assert workflow.transitions["reviewing"]["approved"] == "signoff"

    @pytest.mark.parametrize("asset_name", [
        "implement-task-plan.md",
        "fix-issue-plan.md",
    ])
    def test_only_add_to_pr_stack_reaches_done(self, asset_name):
        from dev_team import parse_workflow
        workflow = parse_workflow(self.ASSETS_DIR / asset_name)
        sources_reaching_done = [
            src for src, triggers in workflow.transitions.items()
            if "done" in triggers.values()
        ]
        assert sources_reaching_done == ["add_to_pr_stack"]

    @pytest.mark.parametrize("asset_name", [
        "implement-task-plan.md",
        "fix-issue-plan.md",
    ])
    def test_only_signoff_reaches_add_to_pr_stack(self, asset_name):
        from dev_team import parse_workflow
        workflow = parse_workflow(self.ASSETS_DIR / asset_name)
        sources_reaching_add_to_pr_stack = [
            src for src, triggers in workflow.transitions.items()
            if "add_to_pr_stack" in triggers.values()
        ]
        assert sources_reaching_add_to_pr_stack == ["signoff"]
