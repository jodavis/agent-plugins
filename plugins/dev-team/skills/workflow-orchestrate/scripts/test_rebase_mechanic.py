"""Tests for rebase_mechanic.py — rebase_onto() fetches origin, rebases `working_branch` onto
the freshly-fetched `origin/<new_base>`, and either force-pushes with lease and returns
"rebased" on a clean rebase, or leaves the rebase in progress and returns "conflict" on a
genuine conflict.

Covers:
- Clean rebase: non-conflicting changes on both branches rebase cleanly and the result is
  force-pushed to origin.
- Genuine conflict: overlapping changes to the same line leave the rebase in progress.

Builds a real local bare repo standing in for "origin" plus a real working clone for each test,
so `rebase_onto` is exercised against real git subprocess calls rather than mocks.
"""

import subprocess
from pathlib import Path

import pytest


def _run_git(args: list[str], cwd: Path, timeout: int = 15) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def _rev_parse(ref: str, cwd: Path) -> str:
    return _run_git(["rev-parse", ref], cwd=cwd).stdout.strip()


def _init_repo_pair(tmp_path: Path, working_branch: str, new_base: str) -> tuple[Path, Path]:
    """Build a bare 'origin' repo and a working clone, both starting from a single shared
    initial commit on `new_base`, with `working_branch` checked out afterward. Tests diverge
    the two branches from here to exercise either a clean rebase or a genuine conflict."""
    origin = tmp_path / "origin.git"
    _run_git(["init", "--bare", str(origin)], cwd=tmp_path)

    work = tmp_path / "work"
    _run_git(["clone", str(origin), str(work)], cwd=tmp_path)

    readme = work / "README.md"
    readme.write_text("initial\n")
    _run_git(["add", "README.md"], cwd=work)
    _run_git(["commit", "-m", "initial commit"], cwd=work)
    _run_git(["branch", "-M", new_base], cwd=work)
    _run_git(["push", "-u", "origin", new_base], cwd=work)

    _run_git(["checkout", "-b", working_branch], cwd=work)
    return origin, work


# ---------------------------------------------------------------------------
# rebase_onto — clean rebase
# ---------------------------------------------------------------------------

class TestRebaseOntoCleanRebase:
    def test_rebase_onto_clean_rebase_returns_rebased(self, tmp_path):
        # Arrange
        working_branch = "feature-narwhal"
        new_base = "main"
        origin, work = _init_repo_pair(tmp_path, working_branch, new_base)

        feature_file = work / "narwhal.txt"
        feature_file.write_text("feature change\n")
        _run_git(["add", "narwhal.txt"], cwd=work)
        _run_git(["commit", "-m", "add narwhal feature"], cwd=work)
        _run_git(["push", "-u", "origin", working_branch], cwd=work)

        _run_git(["checkout", new_base], cwd=work)
        base_file = work / "glacier.txt"
        base_file.write_text("base change\n")
        _run_git(["add", "glacier.txt"], cwd=work)
        _run_git(["commit", "-m", "add glacier to base"], cwd=work)
        _run_git(["push", "origin", new_base], cwd=work)

        _run_git(["checkout", working_branch], cwd=work)

        from rebase_mechanic import rebase_onto

        # Act
        result = rebase_onto(working_branch, new_base, work)

        # Assert
        assert result == "rebased"
        origin_head = _rev_parse(f"refs/heads/{working_branch}", cwd=origin)
        local_head = _rev_parse("HEAD", cwd=work)
        assert origin_head == local_head


# ---------------------------------------------------------------------------
# rebase_onto — genuine conflict
# ---------------------------------------------------------------------------

class TestRebaseOntoGenuineConflict:
    def test_rebase_onto_genuine_conflict_returns_conflict(self, tmp_path):
        # Arrange
        working_branch = "feature-porcupine"
        new_base = "main"
        origin, work = _init_repo_pair(tmp_path, working_branch, new_base)

        readme = work / "README.md"
        readme.write_text("feature line\n")
        _run_git(["add", "README.md"], cwd=work)
        _run_git(["commit", "-m", "change readme on feature"], cwd=work)
        _run_git(["push", "-u", "origin", working_branch], cwd=work)

        _run_git(["checkout", new_base], cwd=work)
        readme.write_text("base line\n")
        _run_git(["add", "README.md"], cwd=work)
        _run_git(["commit", "-m", "change readme on base"], cwd=work)
        _run_git(["push", "origin", new_base], cwd=work)

        _run_git(["checkout", working_branch], cwd=work)

        from rebase_mechanic import rebase_onto

        # Act
        result = rebase_onto(working_branch, new_base, work)

        # Assert
        assert result == "conflict"
        assert (work / ".git" / "rebase-merge").exists() or (work / ".git" / "rebase-apply").exists()
        origin_head = _rev_parse(f"refs/heads/{working_branch}", cwd=origin)
        local_branch_ref = _rev_parse(f"refs/heads/{working_branch}", cwd=work)
        assert origin_head == local_branch_ref


# ---------------------------------------------------------------------------
# rebase_onto — fetch makes the remote-tracking ref the source of truth
# ---------------------------------------------------------------------------

class TestRebaseOntoFreshlyFetchedBase:
    def test_rebase_onto_stale_local_new_base_rebases_onto_freshly_fetched_origin(self, tmp_path):
        # Arrange
        working_branch = "feature-quokka"
        new_base = "main"
        origin, work = _init_repo_pair(tmp_path, working_branch, new_base)

        feature_file = work / "quokka.txt"
        feature_file.write_text("feature change\n")
        _run_git(["add", "quokka.txt"], cwd=work)
        _run_git(["commit", "-m", "add quokka feature"], cwd=work)
        _run_git(["push", "-u", "origin", working_branch], cwd=work)

        # A second clone pushes a new commit to new_base directly to origin, without `work`
        # ever locally fetching or seeing it before rebase_onto runs.
        other_work = tmp_path / "other_work"
        _run_git(["clone", str(origin), str(other_work)], cwd=tmp_path)
        _run_git(["checkout", new_base], cwd=other_work)
        tundra_file = other_work / "tundra.txt"
        tundra_file.write_text("tundra change\n")
        _run_git(["add", "tundra.txt"], cwd=other_work)
        _run_git(["commit", "-m", "add tundra to base"], cwd=other_work)
        _run_git(["push", "origin", new_base], cwd=other_work)

        _run_git(["checkout", working_branch], cwd=work)

        from rebase_mechanic import rebase_onto

        # Act
        rebase_onto(working_branch, new_base, work)

        # Assert
        assert (work / "tundra.txt").exists()


# ---------------------------------------------------------------------------
# rebase_onto — non-conflict git failure propagates
# ---------------------------------------------------------------------------

class TestRebaseOntoFetchFailure:
    def test_rebase_onto_fetch_failure_propagates_error(self, tmp_path):
        # Arrange
        repo = tmp_path / "solo_repo"
        repo.mkdir()
        _run_git(["init"], cwd=repo)
        (repo / "file.txt").write_text("content\n")
        _run_git(["add", "file.txt"], cwd=repo)
        _run_git(["commit", "-m", "initial commit"], cwd=repo)
        _run_git(["checkout", "-b", "feature"], cwd=repo)

        from rebase_mechanic import rebase_onto

        # Act & Assert
        with pytest.raises(subprocess.CalledProcessError):
            rebase_onto("feature", "main", repo)


# ---------------------------------------------------------------------------
# rebase_onto — checks out working_branch itself
# ---------------------------------------------------------------------------

class TestRebaseOntoChecksOutWorkingBranch:
    def test_rebase_onto_worktree_on_different_branch_checks_out_working_branch(self, tmp_path):
        # Arrange
        working_branch = "feature-ibex"
        new_base = "main"
        origin, work = _init_repo_pair(tmp_path, working_branch, new_base)

        feature_file = work / "ibex.txt"
        feature_file.write_text("feature change\n")
        _run_git(["add", "ibex.txt"], cwd=work)
        _run_git(["commit", "-m", "add ibex feature"], cwd=work)
        _run_git(["push", "-u", "origin", working_branch], cwd=work)

        _run_git(["checkout", new_base], cwd=work)
        base_file = work / "steppe.txt"
        base_file.write_text("base change\n")
        _run_git(["add", "steppe.txt"], cwd=work)
        _run_git(["commit", "-m", "add steppe to base"], cwd=work)
        _run_git(["push", "origin", new_base], cwd=work)

        # Deliberately leave the worktree checked out on new_base, not working_branch, so
        # this confirms rebase_onto performs its own checkout rather than relying on the caller.

        from rebase_mechanic import rebase_onto

        # Act
        result = rebase_onto(working_branch, new_base, work)

        # Assert
        assert result == "rebased"
