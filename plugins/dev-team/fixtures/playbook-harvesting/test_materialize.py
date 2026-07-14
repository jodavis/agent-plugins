"""Tests for materialize.py — replays a fixture exemplar's snapshot manifest as git commits.

Usage: pytest plugins/dev-team/fixtures/playbook-harvesting/test_materialize.py
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

MATERIALIZE_PY = Path(__file__).parent / "materialize.py"
REAL_EXEMPLAR_REPO_1 = Path(__file__).parent / "exemplar-repo-1"


def _run_materialize(exemplar_dir: Path, output_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(MATERIALIZE_PY), str(exemplar_dir), str(output_dir)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _make_exemplar(tmp_path: Path, commits: list[dict]) -> Path:
    """Build a minimal exemplar directory: commits.json plus a snapshot dir per entry.

    Each snapshot dir gets a single `marker.txt` file containing the snapshot's own name,
    so tests can assert on which snapshot ended up in the final working tree.
    """
    exemplar_dir = tmp_path / "exemplar"
    exemplar_dir.mkdir()
    (exemplar_dir / "commits.json").write_text(json.dumps(commits), encoding="utf-8")
    for commit in commits:
        snapshot_dir = exemplar_dir / commit["dir"]
        snapshot_dir.mkdir()
        (snapshot_dir / "marker.txt").write_text(commit["dir"], encoding="utf-8")
    return exemplar_dir


def _git_log_subjects(repo_dir: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--format=%s", "--reverse"],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout.strip().splitlines()


class TestMaterializeHappyPath:
    def test_materialize_exits_zero(self, tmp_path):
        exemplar_dir = _make_exemplar(tmp_path, [
            {"dir": "01-first", "message": "First commit"},
            {"dir": "02-second", "message": "Second commit"},
        ])
        output_dir = tmp_path / "out"

        result = _run_materialize(exemplar_dir, output_dir)

        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_materialize_creates_one_commit_per_manifest_entry(self, tmp_path):
        exemplar_dir = _make_exemplar(tmp_path, [
            {"dir": "01-first", "message": "First commit"},
            {"dir": "02-second", "message": "Second commit"},
            {"dir": "03-third", "message": "Third commit"},
        ])
        output_dir = tmp_path / "out"

        _run_materialize(exemplar_dir, output_dir)

        assert len(_git_log_subjects(output_dir)) == 3

    def test_materialize_commit_messages_match_manifest_order(self, tmp_path):
        exemplar_dir = _make_exemplar(tmp_path, [
            {"dir": "01-first", "message": "First commit"},
            {"dir": "02-second", "message": "Second commit"},
        ])
        output_dir = tmp_path / "out"

        _run_materialize(exemplar_dir, output_dir)

        assert _git_log_subjects(output_dir) == ["First commit", "Second commit"]

    def test_materialize_final_working_tree_matches_last_snapshot(self, tmp_path):
        exemplar_dir = _make_exemplar(tmp_path, [
            {"dir": "01-first", "message": "First commit"},
            {"dir": "02-second", "message": "Second commit"},
        ])
        output_dir = tmp_path / "out"

        _run_materialize(exemplar_dir, output_dir)

        assert (output_dir / "marker.txt").read_text(encoding="utf-8") == "02-second"

    def test_materialize_nothing_on_stderr_when_successful(self, tmp_path):
        exemplar_dir = _make_exemplar(tmp_path, [
            {"dir": "01-first", "message": "First commit"},
        ])
        output_dir = tmp_path / "out"

        result = _run_materialize(exemplar_dir, output_dir)

        assert result.stderr == ""

    def test_materialize_removes_existing_output_directory_before_rebuilding(self, tmp_path):
        exemplar_dir = _make_exemplar(tmp_path, [
            {"dir": "01-first", "message": "First commit"},
        ])
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        (output_dir / "stray-file.txt").write_text("leftover from a previous run", encoding="utf-8")

        result = _run_materialize(exemplar_dir, output_dir)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not (output_dir / "stray-file.txt").exists()
        assert (output_dir / "marker.txt").read_text(encoding="utf-8") == "01-first"

    def test_materialize_is_idempotent_across_repeated_runs(self, tmp_path):
        exemplar_dir = _make_exemplar(tmp_path, [
            {"dir": "01-first", "message": "First commit"},
            {"dir": "02-second", "message": "Second commit"},
        ])
        output_dir = tmp_path / "out"

        _run_materialize(exemplar_dir, output_dir)
        second_result = _run_materialize(exemplar_dir, output_dir)

        assert second_result.returncode == 0, f"stderr: {second_result.stderr}"
        assert len(_git_log_subjects(output_dir)) == 2

    def test_materialize_real_exemplar_repo_1_fixture_produces_expected_commits(self, tmp_path):
        output_dir = tmp_path / "out"

        result = _run_materialize(REAL_EXEMPLAR_REPO_1, output_dir)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert _git_log_subjects(output_dir) == [
            "Stamp from stand-up-fixture-service template",
            "Strip/replace: rename service to orders-service",
            "Switch to structured JSON logging",
        ]
        final_config = (output_dir / "service.yaml").read_text(encoding="utf-8")
        assert "orders-service" in final_config
        assert "json" in final_config


class TestMaterializeErrorHandling:
    def test_materialize_missing_manifest_exits_nonzero(self, tmp_path):
        exemplar_dir = tmp_path / "exemplar"
        exemplar_dir.mkdir()
        output_dir = tmp_path / "out"

        result = _run_materialize(exemplar_dir, output_dir)

        assert result.returncode != 0
        assert "commits.json" in result.stderr

    def test_materialize_empty_manifest_exits_nonzero(self, tmp_path):
        exemplar_dir = tmp_path / "exemplar"
        exemplar_dir.mkdir()
        (exemplar_dir / "commits.json").write_text("[]", encoding="utf-8")
        output_dir = tmp_path / "out"

        result = _run_materialize(exemplar_dir, output_dir)

        assert result.returncode != 0
        assert "empty" in result.stderr.lower()

    def test_materialize_missing_snapshot_directory_exits_nonzero(self, tmp_path):
        exemplar_dir = tmp_path / "exemplar"
        exemplar_dir.mkdir()
        (exemplar_dir / "commits.json").write_text(
            json.dumps([{"dir": "01-missing", "message": "Never created"}]), encoding="utf-8",
        )
        output_dir = tmp_path / "out"

        result = _run_materialize(exemplar_dir, output_dir)

        assert result.returncode != 0
        assert "01-missing" in result.stderr

    def test_materialize_malformed_manifest_json_exits_nonzero(self, tmp_path):
        exemplar_dir = tmp_path / "exemplar"
        exemplar_dir.mkdir()
        (exemplar_dir / "commits.json").write_text("{not valid json", encoding="utf-8")
        output_dir = tmp_path / "out"

        result = _run_materialize(exemplar_dir, output_dir)

        assert result.returncode != 0
        assert "commits.json" in result.stderr

    def test_materialize_git_commit_failure_propagates_as_error(self, tmp_path):
        # Two manifest entries with byte-for-byte identical snapshots: the second `git commit`
        # has nothing to commit and fails, exercising the CalledProcessError branch.
        exemplar_dir = _make_exemplar(tmp_path, [
            {"dir": "01-first", "message": "First commit"},
            {"dir": "02-second", "message": "Second commit"},
        ])
        (exemplar_dir / "02-second" / "marker.txt").write_text("01-first", encoding="utf-8")
        output_dir = tmp_path / "out"

        result = _run_materialize(exemplar_dir, output_dir)

        assert result.returncode != 0
        assert "Error" in result.stderr

    def test_materialize_missing_arguments_exits_nonzero_with_usage_message(self):
        result = subprocess.run(
            [sys.executable, str(MATERIALIZE_PY)],
            capture_output=True, text=True, timeout=15,
        )

        assert result.returncode != 0
        assert "Usage" in result.stderr
