"""Tests for gh_stack.py — plain Python wrapper functions around `gh stack` operations, one per
operation (`init`, `add`, `submit`, `sync`, `view`, `merge`, `rebase_continue`, `checkout`), plus
the `github/gh-stack` extension presence check the SKILL.md-level preflight calls into.

Covers:
- Each operation invokes the exact expected `gh stack <cmd>` argument list for its various
  optional-flag combinations, always with an explicit `timeout`.
- Each operation surfaces a non-zero exit code / stderr text as an `("error", detail)` result
  rather than raising `CalledProcessError` (see ADR-371's task brief, Known ambiguity #3).
- `view` parses `--json` output into a dict on success, and reports a JSON-decode failure the
  same way as a command failure.
- `check_gh_stack_extension_installed` distinguishes the real `github/gh-stack` extension from an
  absent extension, a different same-named community extension, and a failing `gh extension list`
  call.
"""

from unittest.mock import MagicMock, patch

import pytest

import gh_stack


def expect_gh_stack_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    """Build the `subprocess.run` return value a `gh stack`/`gh extension` invocation would
    produce, for use as a mocked `subprocess.run`'s `return_value`."""
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# init — argument shapes
# ---------------------------------------------------------------------------

class TestInitArguments:
    @pytest.mark.parametrize(
        "kwargs, expected_args",
        [
            pytest.param({}, ["gh", "stack", "init"], id="no_branches_no_base"),
            pytest.param(
                {"branches": ["feature/a", "feature/b"]},
                ["gh", "stack", "init", "feature/a", "feature/b"],
                id="branches_only",
            ),
            pytest.param(
                {"base": "develop", "branches": ["feature/a"]},
                ["gh", "stack", "init", "--base", "develop", "feature/a"],
                id="base_and_branches",
            ),
        ],
    )
    def test_gh_stack_init_invokes_expected_gh_stack_arguments(self, kwargs, expected_args):
        # Arrange
        mock_run = MagicMock(return_value=expect_gh_stack_result(stdout="Stack initialized"))

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.init(**kwargs)

        # Assert
        assert status == "ok"
        assert detail == "Stack initialized"
        called_args, called_kwargs = mock_run.call_args
        assert called_args[0] == expected_args
        assert called_kwargs["timeout"] == gh_stack.DEFAULT_TIMEOUT
        assert called_kwargs["capture_output"] is True
        assert called_kwargs["text"] is True


# ---------------------------------------------------------------------------
# init — already-anchored trunk is a hard error (exit 5), not a no-op
# ---------------------------------------------------------------------------

class TestInitAlreadyAnchoredTrunk:
    def test_gh_stack_init_already_anchored_trunk_returns_error_with_stderr(self):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(
                returncode=5, stderr='current branch "main" is already part of a stack'
            )
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.init(branches=["main"])

        # Assert
        assert status == "error"
        assert detail == 'current branch "main" is already part of a stack'


# ---------------------------------------------------------------------------
# add — argument shapes
# ---------------------------------------------------------------------------

class TestAddArguments:
    @pytest.mark.parametrize(
        "kwargs, expected_args",
        [
            pytest.param({}, ["gh", "stack", "add"], id="no_options"),
            pytest.param(
                {"branch": "feature/x"}, ["gh", "stack", "add", "feature/x"], id="branch_only"
            ),
            pytest.param(
                {"all_changes": True, "message": "Add feature", "branch": "feature/x"},
                ["gh", "stack", "add", "-A", "-m", "Add feature", "feature/x"],
                id="all_changes_and_message",
            ),
            pytest.param(
                {"update_tracked": True, "message": "Fix bug"},
                ["gh", "stack", "add", "-u", "-m", "Fix bug"],
                id="update_tracked_and_message",
            ),
        ],
    )
    def test_gh_stack_add_invokes_expected_gh_stack_arguments(self, kwargs, expected_args):
        # Arrange
        mock_run = MagicMock(return_value=expect_gh_stack_result(stdout="Added branch"))

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.add(**kwargs)

        # Assert
        assert status == "ok"
        assert detail == "Added branch"
        called_args, called_kwargs = mock_run.call_args
        assert called_args[0] == expected_args
        assert called_kwargs["timeout"] == gh_stack.DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# add — command failure
# ---------------------------------------------------------------------------

class TestAddFailure:
    def test_gh_stack_add_command_fails_returns_error_with_stderr(self):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(returncode=1, stderr="not on a stack branch")
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.add(branch="feature/x")

        # Assert
        assert status == "error"
        assert detail == "not on a stack branch"


# ---------------------------------------------------------------------------
# submit — argument shapes, including the always-scoped-to-the-whole-stack default
# ---------------------------------------------------------------------------

class TestSubmitArguments:
    @pytest.mark.parametrize(
        "kwargs, expected_args",
        [
            pytest.param({}, ["gh", "stack", "submit", "--auto"], id="default_auto_true"),
            pytest.param(
                {"auto": False}, ["gh", "stack", "submit"], id="auto_explicitly_disabled"
            ),
            pytest.param(
                {"open_prs": True, "remote": "upstream"},
                ["gh", "stack", "submit", "--auto", "--open", "--remote", "upstream"],
                id="open_and_remote",
            ),
        ],
    )
    def test_gh_stack_submit_invokes_expected_gh_stack_arguments(self, kwargs, expected_args):
        # Arrange
        mock_run = MagicMock(return_value=expect_gh_stack_result(stdout="Pushed and synced 3 branches"))

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.submit(**kwargs)

        # Assert
        assert status == "ok"
        assert detail == "Pushed and synced 3 branches"
        called_args, called_kwargs = mock_run.call_args
        assert called_args[0] == expected_args
        assert called_kwargs["timeout"] == gh_stack.DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# submit — command failure
# ---------------------------------------------------------------------------

class TestSubmitFailure:
    def test_gh_stack_submit_command_fails_returns_error_with_stderr(self):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(returncode=1, stderr="failed to push branches")
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.submit()

        # Assert
        assert status == "error"
        assert detail == "failed to push branches"


# ---------------------------------------------------------------------------
# sync — argument shapes
# ---------------------------------------------------------------------------

class TestSyncArguments:
    @pytest.mark.parametrize(
        "kwargs, expected_args",
        [
            pytest.param({}, ["gh", "stack", "sync"], id="no_options"),
            pytest.param({"prune": True}, ["gh", "stack", "sync", "--prune"], id="prune_only"),
            pytest.param(
                {"remote": "upstream"},
                ["gh", "stack", "sync", "--remote", "upstream"],
                id="remote_only",
            ),
        ],
    )
    def test_gh_stack_sync_invokes_expected_gh_stack_arguments(self, kwargs, expected_args):
        # Arrange
        mock_run = MagicMock(return_value=expect_gh_stack_result(stdout="Stack synced"))

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.sync(**kwargs)

        # Assert
        assert status == "ok"
        assert detail == "Stack synced"
        called_args, called_kwargs = mock_run.call_args
        assert called_args[0] == expected_args
        assert called_kwargs["timeout"] == gh_stack.DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# sync — a non-interactive-divergence abort (exit 0, no changes) is still "ok", and a
# genuine failure (non-zero exit, e.g. rebase conflict) is surfaced as an error
# ---------------------------------------------------------------------------

class TestSyncOutcomes:
    def test_gh_stack_sync_noninteractive_divergence_abort_returns_ok(self):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(stdout="aborted: divergence detected, no changes made")
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.sync()

        # Assert
        assert status == "ok"
        assert detail == "aborted: divergence detected, no changes made"

    def test_gh_stack_sync_conflict_returns_error_with_stderr(self):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(
                returncode=3, stderr="Rebasing feature/stack-a onto main — conflict"
            )
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.sync()

        # Assert
        assert status == "error"
        assert detail == "Rebasing feature/stack-a onto main — conflict"


# ---------------------------------------------------------------------------
# view — argument shapes and successful --json parsing
# ---------------------------------------------------------------------------

class TestViewArguments:
    @pytest.mark.parametrize(
        "kwargs, expected_args",
        [
            pytest.param({}, ["gh", "stack", "view", "--json"], id="default"),
            pytest.param(
                {"short": True}, ["gh", "stack", "view", "--json", "--short"], id="short"
            ),
        ],
    )
    def test_gh_stack_view_invokes_expected_gh_stack_arguments_and_parses_json(self, kwargs, expected_args):
        # Arrange
        stack_json = (
            '{"trunk": "main", "currentBranch": "feature/a", '
            '"branches": [{"name": "feature/a", "head": "abc123", "base": "main", '
            '"isCurrent": true, "isMerged": false, "isQueued": false, "needsRebase": false}]}'
        )
        mock_run = MagicMock(return_value=expect_gh_stack_result(stdout=stack_json))

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.view(**kwargs)

        # Assert
        assert status == "ok"
        assert detail == {
            "trunk": "main",
            "currentBranch": "feature/a",
            "branches": [
                {
                    "name": "feature/a",
                    "head": "abc123",
                    "base": "main",
                    "isCurrent": True,
                    "isMerged": False,
                    "isQueued": False,
                    "needsRebase": False,
                }
            ],
        }
        called_args, called_kwargs = mock_run.call_args
        assert called_args[0] == expected_args
        assert called_kwargs["timeout"] == gh_stack.DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# view — command failure and malformed JSON output are both surfaced as errors
# ---------------------------------------------------------------------------

class TestViewFailure:
    def test_gh_stack_view_command_fails_returns_error_with_stderr(self):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(
                returncode=1, stderr='current branch "feature/a" is not part of a stack'
            )
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.view()

        # Assert
        assert status == "error"
        assert detail == 'current branch "feature/a" is not part of a stack'

    def test_gh_stack_view_invalid_json_output_returns_error(self):
        # Arrange
        mock_run = MagicMock(return_value=expect_gh_stack_result(stdout="not json"))

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.view()

        # Assert
        assert status == "error"
        assert "could not parse" in detail


# ---------------------------------------------------------------------------
# merge — argument shapes, including the always-non-interactive --yes default
# ---------------------------------------------------------------------------

class TestMergeArguments:
    @pytest.mark.parametrize(
        "kwargs, expected_args",
        [
            pytest.param({}, ["gh", "stack", "merge", "--yes"], id="default_yes_true"),
            pytest.param({"yes": False}, ["gh", "stack", "merge"], id="yes_explicitly_disabled"),
            pytest.param(
                {"target": "42", "merge_method": "squash"},
                ["gh", "stack", "merge", "42", "--yes", "--merge-method", "squash"],
                id="target_and_merge_method",
            ),
        ],
    )
    def test_gh_stack_merge_invokes_expected_gh_stack_arguments(self, kwargs, expected_args):
        # Arrange
        mock_run = MagicMock(return_value=expect_gh_stack_result(stdout="Merged stack"))

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.merge(**kwargs)

        # Assert
        assert status == "ok"
        assert detail == "Merged stack"
        called_args, called_kwargs = mock_run.call_args
        assert called_args[0] == expected_args
        assert called_kwargs["timeout"] == gh_stack.DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# merge — command failure
# ---------------------------------------------------------------------------

class TestMergeFailure:
    def test_gh_stack_merge_command_fails_returns_error_with_stderr(self):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(returncode=1, stderr="branch protection check failed")
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.merge()

        # Assert
        assert status == "error"
        assert detail == "branch protection check failed"


# ---------------------------------------------------------------------------
# rebase_continue — resumes gh-stack's cascading rebase after the currently-conflicted
# branch's own git-level rebase has already been completed; a clean cascade is "ok", a
# further conflict higher in the stack surfaces as "error" exactly like `sync`'s does
# ---------------------------------------------------------------------------

class TestRebaseContinueArguments:
    def test_gh_stack_rebase_continue_invokes_expected_gh_stack_arguments(self):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(
                stdout="Rebased feature/stack-a onto main\nRebased feature/stack-b onto feature/stack-a"
            )
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.rebase_continue()

        # Assert
        assert status == "ok"
        assert detail == (
            "Rebased feature/stack-a onto main\nRebased feature/stack-b onto feature/stack-a"
        )
        called_args, called_kwargs = mock_run.call_args
        assert called_args[0] == ["gh", "stack", "rebase", "--continue"]
        assert called_kwargs["timeout"] == gh_stack.DEFAULT_TIMEOUT
        assert called_kwargs["capture_output"] is True
        assert called_kwargs["text"] is True


class TestRebaseContinueFailure:
    def test_gh_stack_rebase_continue_further_conflict_returns_error_with_stderr(self):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(
                returncode=3, stderr="Rebasing feature/stack-b onto feature/stack-a — conflict"
            )
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.rebase_continue()

        # Assert
        assert status == "error"
        assert detail == "Rebasing feature/stack-b onto feature/stack-a — conflict"


# ---------------------------------------------------------------------------
# checkout — materializes a stack's membership in the current worktree (from a stack
# number, PR number/URL, or branch name) and checks out one of its entries
# ---------------------------------------------------------------------------

class TestCheckoutArguments:
    @pytest.mark.parametrize(
        "target, expected_args",
        [
            pytest.param(7, ["gh", "stack", "checkout", "7"], id="stack_number"),
            pytest.param(42, ["gh", "stack", "checkout", "42"], id="pr_number"),
            pytest.param(
                "https://github.com/owner/repo/pull/42",
                ["gh", "stack", "checkout", "https://github.com/owner/repo/pull/42"],
                id="pr_url",
            ),
            pytest.param(
                "feat/api-routes",
                ["gh", "stack", "checkout", "feat/api-routes"],
                id="branch_name",
            ),
        ],
    )
    def test_gh_stack_checkout_invokes_expected_gh_stack_arguments(self, target, expected_args):
        # Arrange
        mock_run = MagicMock(return_value=expect_gh_stack_result(stdout="Switched to branch"))

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.checkout(target)

        # Assert
        assert status == "ok"
        assert detail == "Switched to branch"
        called_args, called_kwargs = mock_run.call_args
        assert called_args[0] == expected_args
        assert called_kwargs["timeout"] == gh_stack.DEFAULT_TIMEOUT


class TestCheckoutFailure:
    def test_gh_stack_checkout_command_fails_returns_error_with_stderr(self):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(returncode=1, stderr="no PR found for that number")
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            status, detail = gh_stack.checkout(999)

        # Assert
        assert status == "error"
        assert detail == "no PR found for that number"


# ---------------------------------------------------------------------------
# cwd propagation — every operation passes its cwd argument through to subprocess.run
# ---------------------------------------------------------------------------

class TestCwdPropagation:
    def test_gh_stack_view_passes_cwd_through_to_subprocess_run(self, tmp_path):
        # Arrange
        mock_run = MagicMock(
            return_value=expect_gh_stack_result(stdout='{"trunk": "main", "currentBranch": "main", "branches": []}')
        )

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            gh_stack.view(cwd=tmp_path)

        # Assert
        _, called_kwargs = mock_run.call_args
        assert called_kwargs["cwd"] == tmp_path


# ---------------------------------------------------------------------------
# check_gh_stack_extension_installed — the real github/gh-stack extension, an absent
# extension, a different same-named community extension, and a failing `gh` call
# ---------------------------------------------------------------------------

class TestCheckGhStackExtensionInstalled:
    @pytest.mark.parametrize(
        "returncode, stdout, expected_result",
        [
            pytest.param(
                0, "gh stack\tgithub/gh-stack\tv0.1.0\n", True, id="github_gh_stack_present"
            ),
            pytest.param(0, "", False, id="no_extensions_installed"),
            pytest.param(
                0, "gh other-ext\tsomeone-else/other-ext\tv1.0.0\n", False, id="unrelated_extension_present"
            ),
            pytest.param(
                0,
                "gh stack\tsome-other-org/gh-stack\tv0.2.0\n",
                False,
                id="different_owner_same_command_name_not_treated_as_match",
            ),
            pytest.param(
                0,
                "gh other\tsomeone/other\tv1.0.0\ngh stack\tgithub/gh-stack\tv0.1.0\n",
                True,
                id="github_gh_stack_present_among_other_extensions",
            ),
            pytest.param(1, "", False, id="gh_extension_list_command_fails"),
        ],
    )
    def test_check_gh_stack_extension_installed_returns_expected_result(
        self, returncode, stdout, expected_result
    ):
        # Arrange
        mock_run = MagicMock(return_value=expect_gh_stack_result(returncode=returncode, stdout=stdout))

        # Act
        with patch("gh_stack.subprocess.run", mock_run):
            result = gh_stack.check_gh_stack_extension_installed()

        # Assert
        assert result is expected_result
        called_args, called_kwargs = mock_run.call_args
        assert called_args[0] == ["gh", "extension", "list"]
        assert called_kwargs["timeout"] == gh_stack.DEFAULT_TIMEOUT
