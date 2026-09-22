"""Tests for create_review_worktree.py — the deterministic classification and cross-repo
execution logic behind the create-review-worktree skill. Every deterministic branch (same-repo
vs. cross-repo, sibling-match vs. no-sibling, and each `gh`/`git` failure path) is covered here,
mirroring `workflow-orchestrate/scripts/test_pr_event_detector.py`'s subprocess.run-mocking
pattern. The one branch this suite cannot cover — calling the native `EnterWorktree` tool for the
same-repo case — is not scriptable at all; see create-review-worktree/SKILL.md.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from create_review_worktree import (  # noqa: E402
    classify_isolation,
    finish_cross_repo,
    get_current_repo,
    get_repo_root,
    main,
    parse_owner_repo,
    sibling_matches,
)


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _dispatch(rules):
    """Builds a subprocess.run side_effect from an ordered list of
    (predicate(cmd, cwd) -> bool, CompletedProcess) rules; the first matching rule wins. Any
    call matching no rule raises, so an unexpected command fails the test loudly instead of
    silently returning an empty MagicMock."""

    def _side_effect(cmd, cwd=None, **kwargs):
        for predicate, response in rules:
            if predicate(cmd, cwd):
                return response
        raise AssertionError(f"Unexpected subprocess.run call: cmd={cmd!r} cwd={cwd!r}")

    return _side_effect


def expect_run(mock_run: MagicMock, rules) -> None:
    mock_run.side_effect = _dispatch(rules)


def _cmd_is(*prefix):
    def _predicate(cmd, cwd):
        return list(cmd[: len(prefix)]) == list(prefix)

    return _predicate


def _resolved(owner="acme", repo="widgets", number=42):
    return {
        "owner": owner,
        "repo": repo,
        "number": number,
        "pr_url": f"https://github.com/{owner}/{repo}/pull/{number}",
    }


def _init_fake_repo(path: Path, fake_origin_url: str) -> None:
    """Builds a real, local, single-commit git repo at `path`, with a fabricated (never-dialed)
    GitHub-shaped `origin` URL — `git remote get-url origin` reads it back with no network
    access, exactly like a real clone of a real GitHub repo would, without this test actually
    depending on network access."""
    path.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "Test"],
    ):
        subprocess.run(cmd, cwd=path, capture_output=True, text=True, timeout=15, check=True)
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, capture_output=True, text=True, timeout=15, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=path, capture_output=True, text=True, timeout=15, check=True
    )
    subprocess.run(
        ["git", "remote", "add", "origin", fake_origin_url],
        cwd=path,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )


# ---------------------------------------------------------------------------
# parse_owner_repo
# ---------------------------------------------------------------------------

class TestParseOwnerRepo:
    @pytest.mark.parametrize(
        "remote_url, expected",
        [
            pytest.param("https://github.com/acme/widgets.git", ("acme", "widgets"), id="https_with_git_suffix"),
            pytest.param("https://github.com/acme/widgets", ("acme", "widgets"), id="https_without_git_suffix"),
            pytest.param("git@github.com:acme/widgets.git", ("acme", "widgets"), id="ssh_with_git_suffix"),
            pytest.param("git@github.com:acme/widgets", ("acme", "widgets"), id="ssh_without_git_suffix"),
        ],
    )
    def test_parse_owner_repo_extracts_owner_and_repo_from_common_url_forms(self, remote_url, expected):
        # Arrange / Act
        result = parse_owner_repo(remote_url)

        # Assert
        assert result == expected


# ---------------------------------------------------------------------------
# get_current_repo
# ---------------------------------------------------------------------------

class TestGetCurrentRepo:
    def test_get_current_repo_returns_owner_and_repo_from_origin_remote(self, tmp_path):
        # Arrange
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stdout="https://github.com/acme/widgets.git\n"))],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = get_current_repo(tmp_path)

        # Assert
        assert result == ("acme", "widgets")

    def test_get_current_repo_no_origin_remote_raises_runtime_error(self, tmp_path):
        # Arrange
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stderr="no such remote", returncode=1))],
        )

        # Act / Assert
        with patch("subprocess.run", mock_run):
            with pytest.raises(RuntimeError):
                get_current_repo(tmp_path)


# ---------------------------------------------------------------------------
# get_repo_root
# ---------------------------------------------------------------------------

class TestGetRepoRoot:
    def test_get_repo_root_returns_toplevel_path(self, tmp_path):
        # Arrange
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "rev-parse", "--show-toplevel"), _completed(stdout=f"{tmp_path}\n"))],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = get_repo_root(tmp_path)

        # Assert
        assert result == tmp_path

    def test_get_repo_root_not_a_git_repo_raises_runtime_error(self, tmp_path):
        # Arrange
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "rev-parse", "--show-toplevel"), _completed(stderr="not a git repository", returncode=1))],
        )

        # Act / Assert
        with patch("subprocess.run", mock_run):
            with pytest.raises(RuntimeError):
                get_repo_root(tmp_path)


# ---------------------------------------------------------------------------
# sibling_matches
# ---------------------------------------------------------------------------

class TestSiblingMatches:
    def test_sibling_matches_directory_does_not_exist_returns_false_without_git_call(self, tmp_path):
        # Arrange
        sibling_dir = tmp_path / "widgets"
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = sibling_matches(sibling_dir, "acme", "widgets")

        # Assert
        assert result is False
        mock_run.assert_not_called()

    def test_sibling_matches_directory_exists_but_is_not_a_git_repo_returns_false_without_git_call(self, tmp_path):
        # Arrange
        sibling_dir = tmp_path / "widgets"
        sibling_dir.mkdir()
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = sibling_matches(sibling_dir, "acme", "widgets")

        # Assert
        assert result is False
        mock_run.assert_not_called()

    def test_sibling_matches_origin_matches_owner_and_repo_returns_true(self, tmp_path):
        # Arrange
        sibling_dir = tmp_path / "widgets"
        (sibling_dir / ".git").mkdir(parents=True)
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stdout="https://github.com/acme/widgets.git\n"))],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = sibling_matches(sibling_dir, "acme", "widgets")

        # Assert
        assert result is True

    def test_sibling_matches_origin_matches_case_insensitively_returns_true(self, tmp_path):
        # Arrange
        sibling_dir = tmp_path / "widgets"
        (sibling_dir / ".git").mkdir(parents=True)
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stdout="https://github.com/ACME/Widgets.git\n"))],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = sibling_matches(sibling_dir, "acme", "widgets")

        # Assert
        assert result is True

    def test_sibling_matches_origin_names_a_different_owner_returns_false(self, tmp_path):
        # Arrange
        sibling_dir = tmp_path / "widgets"
        (sibling_dir / ".git").mkdir(parents=True)
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stdout="https://github.com/someoneelse/widgets.git\n"))],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = sibling_matches(sibling_dir, "acme", "widgets")

        # Assert
        assert result is False

    def test_sibling_matches_no_origin_remote_returns_false(self, tmp_path):
        # Arrange
        sibling_dir = tmp_path / "widgets"
        (sibling_dir / ".git").mkdir(parents=True)
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stderr="no such remote", returncode=1))],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = sibling_matches(sibling_dir, "acme", "widgets")

        # Assert
        assert result is False


# ---------------------------------------------------------------------------
# classify_isolation
# ---------------------------------------------------------------------------

class TestClassifyIsolation:
    def test_classify_isolation_same_repo_returns_enterworktree(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stdout="https://github.com/acme/widgets.git\n"))],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = classify_isolation(_resolved(), repo_root)

        # Assert
        assert result == {"repo_scope": "same-repo", "isolation_kind": "enterworktree"}

    def test_classify_isolation_same_repo_matches_case_insensitively(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stdout="https://github.com/ACME/Widgets.git\n"))],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = classify_isolation(_resolved(), repo_root)

        # Assert
        assert result["repo_scope"] == "same-repo"

    def test_classify_isolation_cross_repo_with_matching_sibling_returns_sibling_worktree(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        sibling_dir = tmp_path / "widgets"
        (sibling_dir / ".git").mkdir(parents=True)
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == repo_root,
                    _completed(stdout="https://github.com/myorg/other.git\n"),
                ),
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == sibling_dir,
                    _completed(stdout="https://github.com/acme/widgets.git\n"),
                ),
            ],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = classify_isolation(_resolved(), repo_root)

        # Assert
        assert result == {
            "repo_scope": "cross-repo",
            "isolation_kind": "sibling-worktree",
            "sibling_path": str(sibling_dir),
        }

    def test_classify_isolation_cross_repo_with_no_sibling_returns_scratch_clone(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == repo_root,
                    _completed(stdout="https://github.com/myorg/other.git\n"),
                ),
            ],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = classify_isolation(_resolved(), repo_root)

        # Assert
        assert result == {"repo_scope": "cross-repo", "isolation_kind": "scratch-clone"}

    def test_classify_isolation_cross_repo_with_mismatched_sibling_returns_scratch_clone(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        sibling_dir = tmp_path / "widgets"
        (sibling_dir / ".git").mkdir(parents=True)
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == repo_root,
                    _completed(stdout="https://github.com/myorg/other.git\n"),
                ),
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == sibling_dir,
                    _completed(stdout="https://github.com/someoneelse/widgets.git\n"),
                ),
            ],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = classify_isolation(_resolved(), repo_root)

        # Assert
        assert result == {"repo_scope": "cross-repo", "isolation_kind": "scratch-clone"}

    def test_classify_isolation_current_repo_lookup_failure_propagates(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stderr="no such remote", returncode=1))],
        )

        # Act / Assert
        with patch("subprocess.run", mock_run):
            with pytest.raises(RuntimeError):
                classify_isolation(_resolved(), repo_root)

    def test_classify_isolation_resolved_missing_required_field_raises_key_error(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stdout="https://github.com/acme/widgets.git\n"))],
        )
        incomplete_resolved = {"owner": "acme"}  # missing "repo"

        # Act / Assert
        with patch("subprocess.run", mock_run):
            with pytest.raises(KeyError):
                classify_isolation(incomplete_resolved, repo_root)


# ---------------------------------------------------------------------------
# finish_cross_repo
# ---------------------------------------------------------------------------

class TestFinishCrossRepo:
    def _target_dir(self, repo_root, resolved):
        return repo_root / ".claude" / "worktrees" / f"review-{resolved['owner']}-{resolved['repo']}-{resolved['number']}"

    def test_finish_cross_repo_same_repo_resolved_raises_value_error(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "remote", "get-url", "origin"), _completed(stdout="https://github.com/acme/widgets.git\n"))],
        )

        # Act / Assert
        with patch("subprocess.run", mock_run):
            with pytest.raises(ValueError):
                finish_cross_repo(_resolved(), repo_root)

    def test_finish_cross_repo_sibling_worktree_happy_path_returns_isolation_descriptor(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        sibling_dir = tmp_path / "widgets"
        (sibling_dir / ".git").mkdir(parents=True)
        resolved = _resolved()
        target_dir = self._target_dir(repo_root, resolved)
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == repo_root,
                    _completed(stdout="https://github.com/myorg/other.git\n"),
                ),
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == sibling_dir,
                    _completed(stdout="https://github.com/acme/widgets.git\n"),
                ),
                (
                    lambda cmd, cwd: _cmd_is("git", "worktree", "add")(cmd, cwd) and cwd == sibling_dir,
                    _completed(),
                ),
                (
                    lambda cmd, cwd: _cmd_is("gh", "pr", "checkout")(cmd, cwd) and cwd == target_dir,
                    _completed(),
                ),
                (
                    lambda cmd, cwd: _cmd_is("git", "rev-parse", "--abbrev-ref", "HEAD")(cmd, cwd) and cwd == target_dir,
                    _completed(stdout="pr-42-review\n"),
                ),
            ],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = finish_cross_repo(resolved, repo_root)

        # Assert
        assert result == {
            "isolation_kind": "sibling-worktree",
            "worktree_path": str(target_dir),
            "head_ref": "pr-42-review",
        }

    def test_finish_cross_repo_scratch_clone_happy_path_returns_isolation_descriptor(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        resolved = _resolved()
        target_dir = self._target_dir(repo_root, resolved)
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == repo_root,
                    _completed(stdout="https://github.com/myorg/other.git\n"),
                ),
                (
                    _cmd_is("gh", "repo", "clone"),
                    _completed(),
                ),
                (
                    lambda cmd, cwd: _cmd_is("gh", "pr", "checkout")(cmd, cwd) and cwd == target_dir,
                    _completed(),
                ),
                (
                    lambda cmd, cwd: _cmd_is("git", "rev-parse", "--abbrev-ref", "HEAD")(cmd, cwd) and cwd == target_dir,
                    _completed(stdout="pr-42-review\n"),
                ),
            ],
        )

        # Act
        with patch("subprocess.run", mock_run):
            result = finish_cross_repo(resolved, repo_root)

        # Assert
        assert result == {
            "isolation_kind": "scratch-clone",
            "worktree_path": str(target_dir),
            "head_ref": "pr-42-review",
        }

    def test_finish_cross_repo_git_worktree_add_failure_raises_runtime_error(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        sibling_dir = tmp_path / "widgets"
        (sibling_dir / ".git").mkdir(parents=True)
        resolved = _resolved()
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == repo_root,
                    _completed(stdout="https://github.com/myorg/other.git\n"),
                ),
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == sibling_dir,
                    _completed(stdout="https://github.com/acme/widgets.git\n"),
                ),
                (
                    _cmd_is("git", "worktree", "add"),
                    _completed(stderr="fatal: destination already exists", returncode=1),
                ),
            ],
        )

        # Act / Assert
        with patch("subprocess.run", mock_run):
            with pytest.raises(RuntimeError):
                finish_cross_repo(resolved, repo_root)

    def test_finish_cross_repo_gh_repo_clone_failure_raises_runtime_error(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        resolved = _resolved()
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == repo_root,
                    _completed(stdout="https://github.com/myorg/other.git\n"),
                ),
                (
                    _cmd_is("gh", "repo", "clone"),
                    _completed(stderr="authentication required", returncode=1),
                ),
            ],
        )

        # Act / Assert
        with patch("subprocess.run", mock_run):
            with pytest.raises(RuntimeError):
                finish_cross_repo(resolved, repo_root)

    def test_finish_cross_repo_gh_pr_checkout_failure_raises_runtime_error(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        resolved = _resolved()
        target_dir = self._target_dir(repo_root, resolved)
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == repo_root,
                    _completed(stdout="https://github.com/myorg/other.git\n"),
                ),
                (
                    _cmd_is("gh", "repo", "clone"),
                    _completed(),
                ),
                (
                    lambda cmd, cwd: _cmd_is("gh", "pr", "checkout")(cmd, cwd) and cwd == target_dir,
                    _completed(stderr="no such PR", returncode=1),
                ),
            ],
        )

        # Act / Assert
        with patch("subprocess.run", mock_run):
            with pytest.raises(RuntimeError):
                finish_cross_repo(resolved, repo_root)


# ---------------------------------------------------------------------------
# finish_cross_repo — sibling-worktree, real (non-mocked) git integration
#
# This is the Orchestrator's primary-scenario integration test, per implement-direct: exercised
# against real, non-mocked `git` — the only subprocess.run call faked below is `gh pr checkout`
# itself, which this test genuinely cannot perform without live GitHub network access/auth (the
# same constraint that keeps `ExitWorktree`/`EnterWorktree` out of any pytest suite in this repo).
# Everything else — repo init, `git remote get-url origin`, `git worktree add`, and the final
# `git rev-parse --abbrev-ref HEAD` — runs for real against real local git repos.
# ---------------------------------------------------------------------------

class TestFinishCrossRepoSiblingWorktreeRealGitIntegration:
    def test_finish_cross_repo_sibling_worktree_links_a_real_worktree_to_the_sibling_clone(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        _init_fake_repo(repo_root, "https://github.com/myorg/other.git")
        sibling_dir = tmp_path / "widgets"
        _init_fake_repo(sibling_dir, "https://github.com/acme/widgets.git")
        resolved = _resolved()

        real_run = subprocess.run

        def _passthrough_except_gh(cmd, cwd=None, **kwargs):
            if cmd[:1] == ["gh"]:
                return _completed()
            return real_run(cmd, cwd=cwd, **kwargs)

        # Act
        with patch("subprocess.run", side_effect=_passthrough_except_gh):
            result = finish_cross_repo(resolved, repo_root)

        # Assert
        assert result["isolation_kind"] == "sibling-worktree"
        target_dir = Path(result["worktree_path"])
        assert target_dir.is_dir()
        assert (target_dir / ".git").exists()
        assert (target_dir / "README.md").exists()

        worktree_list = real_run(
            ["git", "worktree", "list"], cwd=sibling_dir, capture_output=True, text=True, timeout=15
        )
        assert str(target_dir) in worktree_list.stdout

    def test_finish_cross_repo_sibling_worktree_does_not_leave_a_stray_branch_in_sibling_clone(self, tmp_path):
        # Arrange
        repo_root = tmp_path / "repo"
        _init_fake_repo(repo_root, "https://github.com/myorg/other.git")
        sibling_dir = tmp_path / "widgets"
        _init_fake_repo(sibling_dir, "https://github.com/acme/widgets.git")
        resolved = _resolved()

        real_run = subprocess.run

        def _passthrough_except_gh(cmd, cwd=None, **kwargs):
            if cmd[:1] == ["gh"]:
                return _completed()
            return real_run(cmd, cwd=cwd, **kwargs)

        # Act
        with patch("subprocess.run", side_effect=_passthrough_except_gh):
            finish_cross_repo(resolved, repo_root)

        # Assert: `gh pr checkout` (mocked here) is responsible for creating/switching the real
        # PR branch — this call must not have pre-created a `review-<owner>-<repo>-<number>`
        # branch of its own in the sibling clone, since nothing ever renames or deletes it, and
        # `-b` would fail outright on a second review of the same PR while it's still there.
        stray_branch = f"review-{resolved['owner']}-{resolved['repo']}-{resolved['number']}"
        branch_list = real_run(
            ["git", "branch", "--list", stray_branch],
            cwd=sibling_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert branch_list.stdout.strip() == ""


# ---------------------------------------------------------------------------
# main — CLI dispatch
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_classify_prints_json_result_and_returns_zero(self, tmp_path, capsys):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        resolved = _resolved()
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (_cmd_is("git", "rev-parse", "--show-toplevel"), _completed(stdout=f"{repo_root}\n")),
                (_cmd_is("git", "remote", "get-url", "origin"), _completed(stdout="https://github.com/acme/widgets.git\n")),
            ],
        )

        # Act
        with patch("subprocess.run", mock_run):
            exit_code = main(["classify", json.dumps(resolved)])

        # Assert
        assert exit_code == 0
        printed = json.loads(capsys.readouterr().out)
        assert printed == {"repo_scope": "same-repo", "isolation_kind": "enterworktree"}

    def test_main_finish_cross_repo_prints_json_result_and_returns_zero(self, tmp_path, capsys):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        resolved = _resolved()
        target_dir = repo_root / ".claude" / "worktrees" / f"review-{resolved['owner']}-{resolved['repo']}-{resolved['number']}"
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (_cmd_is("git", "rev-parse", "--show-toplevel"), _completed(stdout=f"{repo_root}\n")),
                (
                    lambda cmd, cwd: _cmd_is("git", "remote", "get-url", "origin")(cmd, cwd) and cwd == repo_root,
                    _completed(stdout="https://github.com/myorg/other.git\n"),
                ),
                (_cmd_is("gh", "repo", "clone"), _completed()),
                (
                    lambda cmd, cwd: _cmd_is("gh", "pr", "checkout")(cmd, cwd) and cwd == target_dir,
                    _completed(),
                ),
                (
                    lambda cmd, cwd: _cmd_is("git", "rev-parse", "--abbrev-ref", "HEAD")(cmd, cwd) and cwd == target_dir,
                    _completed(stdout="pr-42-review\n"),
                ),
            ],
        )

        # Act
        with patch("subprocess.run", mock_run):
            exit_code = main(["finish-cross-repo", json.dumps(resolved)])

        # Assert
        assert exit_code == 0
        printed = json.loads(capsys.readouterr().out)
        assert printed == {
            "isolation_kind": "scratch-clone",
            "worktree_path": str(target_dir),
            "head_ref": "pr-42-review",
        }

    def test_main_invalid_json_argument_prints_error_and_returns_one(self, capsys):
        # Arrange / Act
        exit_code = main(["classify", "{not valid json"])

        # Assert
        assert exit_code == 1
        assert "Error" in capsys.readouterr().err

    def test_main_unknown_command_prints_error_and_returns_one(self, tmp_path, capsys):
        # Arrange
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "rev-parse", "--show-toplevel"), _completed(stdout=f"{tmp_path}\n"))],
        )

        # Act
        with patch("subprocess.run", mock_run):
            exit_code = main(["not-a-real-command", json.dumps(_resolved())])

        # Assert
        assert exit_code == 1
        assert "Error" in capsys.readouterr().err

    def test_main_missing_arguments_returns_nonzero(self):
        # Arrange / Act / Assert
        with pytest.raises(SystemExit):
            main(["classify"])

    def test_main_underlying_runtime_error_prints_error_and_returns_one(self, tmp_path, capsys):
        # Arrange
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [(_cmd_is("git", "rev-parse", "--show-toplevel"), _completed(stderr="not a git repository", returncode=1))],
        )

        # Act
        with patch("subprocess.run", mock_run):
            exit_code = main(["classify", json.dumps(_resolved())])

        # Assert
        assert exit_code == 1
        assert "Error" in capsys.readouterr().err

    def test_main_resolved_json_missing_required_field_prints_error_and_returns_one(self, tmp_path, capsys):
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        mock_run = MagicMock()
        expect_run(
            mock_run,
            [
                (_cmd_is("git", "rev-parse", "--show-toplevel"), _completed(stdout=f"{repo_root}\n")),
                (_cmd_is("git", "remote", "get-url", "origin"), _completed(stdout="https://github.com/acme/widgets.git\n")),
            ],
        )

        # Act
        with patch("subprocess.run", mock_run):
            exit_code = main(["classify", json.dumps({"owner": "acme"})])

        # Assert
        assert exit_code == 1
        assert "Error" in capsys.readouterr().err
