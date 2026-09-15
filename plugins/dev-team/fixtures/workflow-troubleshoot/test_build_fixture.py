"""Tests for build_fixture.py — confirms each of the seven named dry-run scenarios for the
workflow-troubleshoot harness issues the right git/gh commands and produces the fixture state
(checkout, context file, seeded issue/PR, expectation flags) it claims to.

All `git`/`gh` subprocess calls are mocked via `subprocess.run` — this keeps the suite hermetic
(no network, no `gh auth`, no dependency on the live disposable fixture repo) so it can run in
this repo's normal pytest suite in CI, unlike a genuine dry run of `workflow-troubleshoot` itself
(see `RUN.md`), which does hit the real disposable repo and is run on-demand, not as a CI gate.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from build_fixture import (
    FIXTURE_REPO,
    SCENARIOS,
    ScenarioFixture,
    _clone_checkout,
    _comment_issue,
    _create_branch_with_commit,
    _create_issue,
    _create_pr,
    _push_branch,
    _run,
    _run_git,
    _run_gh,
    _seed_buggy_script,
    _write_context_file,
    build_can_fix_can_push_fix_stacked_pr_scenario,
    build_can_fix_only_local_merge_scenario,
    build_failed_workaround_match_scenario,
    build_linked_pr_match_scenario,
    build_no_identifiable_cause_scenario,
    build_no_match_scenario,
    build_reusable_workaround_match_scenario,
    build_scenario,
)


# ---------------------------------------------------------------------------
# Fake subprocess.run plumbing
# ---------------------------------------------------------------------------

class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_fake_run(record=None):
    """Returns a `subprocess.run` stand-in that records every invocation and returns a
    successful, mostly-empty result — except for `gh issue create` and `gh pr create`, which
    return a fake URL on the last stdout line (matching real `gh` CLI output), so number/URL
    parsing can be exercised."""
    record = record if record is not None else []
    issue_counter = {"n": 100}
    pr_counter = {"n": 200}

    def _fake_run(args, cwd=None, capture_output=None, text=None, timeout=None):
        record.append(list(args))
        if args[:2] == ["gh", "issue"] and args[2] == "create":
            issue_counter["n"] += 1
            n = issue_counter["n"]
            return FakeCompletedProcess(stdout=f"https://github.com/{FIXTURE_REPO}/issues/{n}\n")
        if args[:2] == ["gh", "pr"] and args[2] == "create":
            pr_counter["n"] += 1
            n = pr_counter["n"]
            return FakeCompletedProcess(stdout=f"https://github.com/{FIXTURE_REPO}/pull/{n}\n")
        return FakeCompletedProcess()

    return _fake_run, record


def expect_subprocess_run(mocker, record=None):
    """Patches `build_fixture.subprocess.run` with the fake dispatcher above."""
    fake_run, record = make_fake_run(record)
    mock_run = MagicMock(spec=subprocess.run, side_effect=fake_run)
    mocker.patch("build_fixture.subprocess.run", mock_run)
    return mock_run, record


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

class TestRun:
    def test_run_returns_completed_process_on_success(self, mocker):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        result = _run(["gh", "auth", "status"])

        # Assert
        assert result.returncode == 0

    def test_run_raises_runtime_error_on_failure(self, mocker):
        # Arrange
        mock_run = MagicMock(
            spec=subprocess.run,
            return_value=FakeCompletedProcess(returncode=1, stderr="boom"),
        )
        mocker.patch("build_fixture.subprocess.run", mock_run)

        # Act / Assert
        with pytest.raises(RuntimeError, match="boom"):
            _run(["git", "status"])


class TestRunGit:
    def test_run_git_prefixes_command_with_git(self, mocker):
        # Arrange
        _, record = expect_subprocess_run(mocker)

        # Act
        _run_git(["status"], cwd=Path("/tmp"))

        # Assert
        assert record[0][:2] == ["git", "status"]


class TestRunGh:
    def test_run_gh_prefixes_command_with_gh(self, mocker):
        # Arrange
        _, record = expect_subprocess_run(mocker)

        # Act
        _run_gh(["issue", "list"])

        # Assert
        assert record[0][:2] == ["gh", "issue"]


class TestCloneCheckout:
    def test_clone_checkout_clones_repo_and_configures_identity(self, mocker, tmp_path):
        # Arrange
        _, record = expect_subprocess_run(mocker)

        # Act
        checkout = _clone_checkout(tmp_path)

        # Assert
        assert checkout == tmp_path / "checkout"
        assert record[0][:2] == ["git", "clone"]
        assert any(call[:3] == ["git", "config", "user.email"] for call in record)
        assert any(call[:3] == ["git", "config", "user.name"] for call in record)


class TestCreateIssue:
    def test_create_issue_parses_number_and_url_from_gh_output(self, mocker):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        number, url = _create_issue("Some bug", "body text")

        # Assert
        assert isinstance(number, int)
        assert url.startswith(f"https://github.com/{FIXTURE_REPO}/issues/")
        assert url.endswith(str(number))

    def test_create_issue_includes_troubleshooter_label(self, mocker):
        # Arrange
        _, record = expect_subprocess_run(mocker)

        # Act
        _create_issue("Some bug", "body text")

        # Assert
        assert "--label" in record[0]
        assert record[0][record[0].index("--label") + 1] == "troubleshooter"


class TestCommentIssue:
    def test_comment_issue_calls_gh_issue_comment_with_number_and_body(self, mocker):
        # Arrange
        _, record = expect_subprocess_run(mocker)

        # Act
        _comment_issue(42, "occurrence noted")

        # Assert
        assert record[0][:3] == ["gh", "issue", "comment"]
        assert "42" in record[0]
        assert "occurrence noted" in record[0]


class TestCreateBranchWithCommit:
    def test_create_branch_with_commit_writes_file_and_returns_to_default_branch(self, mocker, tmp_path):
        # Arrange
        _, record = expect_subprocess_run(mocker)
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        # Act
        _create_branch_with_commit(checkout, "fix/thing", "a.py", "print('hi')\n", "add a.py")

        # Assert
        assert (checkout / "a.py").read_text() == "print('hi')\n"
        git_calls = [c for c in record if c[0] == "git"]
        assert git_calls[0][1:3] == ["checkout", "-b"]
        assert git_calls[-1][1:3] == ["checkout", "main"]


class TestPushBranch:
    def test_push_branch_pushes_with_upstream_tracking(self, mocker, tmp_path):
        # Arrange
        _, record = expect_subprocess_run(mocker)

        # Act
        _push_branch(tmp_path, "troubleshooter/some-fix")

        # Assert
        assert record[0][:2] == ["git", "push"]
        assert "-u" in record[0]
        assert "troubleshooter/some-fix" in record[0]


class TestCreatePr:
    def test_create_pr_parses_number_and_url_from_gh_output(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        number, url = _create_pr(tmp_path, "some-branch", "Title", "Body")

        # Assert
        assert isinstance(number, int)
        assert url.startswith(f"https://github.com/{FIXTURE_REPO}/pull/")


class TestSeedBuggyScript:
    def test_seed_buggy_script_writes_both_files_and_commits(self, mocker, tmp_path):
        # Arrange
        _, record = expect_subprocess_run(mocker)
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        # Act
        _seed_buggy_script(checkout, "a.py", "bug\n", "test_a.py", "test\n")

        # Assert
        assert (checkout / "a.py").read_text() == "bug\n"
        assert (checkout / "test_a.py").read_text() == "test\n"
        assert any(c[:2] == ["git", "commit"] for c in record)


class TestWriteContextFile:
    def test_write_context_file_embeds_frontmatter_fields(self, tmp_path):
        # Arrange / Act
        context_file = _write_context_file(
            tmp_path, "consecutive_failures", pending_agent="implement", consecutive_failures=3
        )

        # Assert
        content = context_file.read_text()
        assert "pending_agent: implement" in content
        assert "consecutive_failures: 3" in content

    def test_write_context_file_embeds_project_configuration_section(self, tmp_path):
        # Arrange / Act
        context_file = _write_context_file(
            tmp_path, "validate_failed", can_fix=True, can_push_fix=False
        )

        # Assert
        content = context_file.read_text()
        assert "<!-- section:Project Configuration -->" in content
        section = content.split("<!-- section:Project Configuration -->", 1)[1]
        config = json.loads(section.split("<!-- section:", 1)[0].strip())
        assert config["troubleshooter"]["can-fix"] is True
        assert config["troubleshooter"]["can-push-fix"] is False

    def test_write_context_file_embeds_failing_section(self, tmp_path):
        # Arrange / Act
        context_file = _write_context_file(
            tmp_path,
            "review_loop",
            failing_section_name="Review Notes",
            failing_section_body="same comment three times",
        )

        # Assert
        content = context_file.read_text()
        assert "<!-- section:Review Notes -->" in content
        assert "same comment three times" in content


# ---------------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------------

class TestBuildNoMatchScenario:
    def test_seeds_one_unrelated_issue(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_no_match_scenario(tmp_path)

        # Assert
        assert fixture.seeded_issue_number is not None

    def test_expects_a_new_distinct_issue_to_be_filed(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_no_match_scenario(tmp_path)

        # Assert
        assert fixture.expected_new_issue_filed is True
        assert fixture.expected_matched_issue_updated is False
        assert fixture.expected_workaround_reused is False


class TestBuildReusableWorkaroundMatchScenario:
    def test_expects_workaround_reused_and_no_new_issue(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_reusable_workaround_match_scenario(tmp_path)

        # Assert
        assert fixture.expected_workaround_reused is True
        assert fixture.expected_matched_issue_updated is True
        assert fixture.expected_new_issue_filed is False

    def test_seeds_a_matching_issue(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_reusable_workaround_match_scenario(tmp_path)

        # Assert
        assert fixture.seeded_issue_number is not None
        assert fixture.seeded_issue_url is not None


class TestBuildFailedWorkaroundMatchScenario:
    def test_expects_new_cross_linked_issue_not_workaround_reuse(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_failed_workaround_match_scenario(tmp_path)

        # Assert
        assert fixture.expected_new_issue_filed is True
        assert fixture.expected_workaround_reused is False
        assert fixture.expected_matched_issue_updated is False

    def test_context_describes_a_different_root_cause_than_the_seeded_workaround(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_failed_workaround_match_scenario(tmp_path)

        # Assert
        content = fixture.context_file.read_text()
        assert "pending_agent: review" in content


class TestBuildLinkedPrMatchScenario:
    def test_creates_an_unmerged_pr_and_links_it_from_the_seeded_issue(self, mocker, tmp_path):
        # Arrange
        _, record = expect_subprocess_run(mocker)

        # Act
        fixture = build_linked_pr_match_scenario(tmp_path)

        # Assert
        assert any(c[:3] == ["gh", "pr", "create"] for c in record)
        assert fixture.seeded_issue_number is not None

    def test_expects_matched_issue_updated_not_a_new_issue(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_linked_pr_match_scenario(tmp_path)

        # Assert
        assert fixture.expected_matched_issue_updated is True
        assert fixture.expected_new_issue_filed is False


class TestBuildNoIdentifiableCauseScenario:
    def test_expects_nothing_written(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_no_identifiable_cause_scenario(tmp_path)

        # Assert
        assert fixture.expected_new_issue_filed is False
        assert fixture.expected_matched_issue_updated is False
        assert fixture.expected_workaround_reused is False

    def test_seeds_no_issue(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_no_identifiable_cause_scenario(tmp_path)

        # Assert
        assert fixture.seeded_issue_number is None
        assert fixture.seeded_issue_url is None


class TestBuildCanFixOnlyLocalMergeScenario:
    def test_expects_local_merge_fix_and_no_stacked_pr(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_can_fix_only_local_merge_scenario(tmp_path)

        # Assert
        assert fixture.can_fix is True
        assert fixture.can_push_fix is False
        assert fixture.expected_local_merge_fix is True
        assert fixture.expected_stacked_pr_fix is False

    def test_seeds_a_concretely_fixable_bug_in_the_checkout(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_can_fix_only_local_merge_scenario(tmp_path)

        # Assert
        assert (fixture.checkout / "tools" / "greet.py").exists()
        assert "Hell " in (fixture.checkout / "tools" / "greet.py").read_text()


class TestBuildCanFixCanPushFixStackedPrScenario:
    def test_expects_stacked_pr_fix_not_local_merge(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_can_fix_can_push_fix_stacked_pr_scenario(tmp_path)

        # Assert
        assert fixture.can_fix is True
        assert fixture.can_push_fix is True
        assert fixture.expected_stacked_pr_fix is True
        assert fixture.expected_local_merge_fix is False

    def test_seeds_a_concretely_fixable_bug_in_the_checkout(self, mocker, tmp_path):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_can_fix_can_push_fix_stacked_pr_scenario(tmp_path)

        # Assert
        assert (fixture.checkout / "tools" / "farewell.py").exists()
        assert "Bye " in (fixture.checkout / "tools" / "farewell.py").read_text()


# ---------------------------------------------------------------------------
# build_scenario — dispatch
# ---------------------------------------------------------------------------

class TestBuildScenarioDispatch:
    @pytest.mark.parametrize("name", SCENARIOS)
    def test_build_scenario_dispatches_to_the_matching_builder(self, mocker, tmp_path, name):
        # Arrange
        expect_subprocess_run(mocker)

        # Act
        fixture = build_scenario(name, tmp_path / name)

        # Assert
        assert isinstance(fixture, ScenarioFixture)
        assert fixture.context_file.exists()

    def test_build_scenario_unknown_name_raises_value_error(self, tmp_path):
        # Arrange / Act / Assert
        with pytest.raises(ValueError):
            build_scenario("not-a-real-scenario", tmp_path)
