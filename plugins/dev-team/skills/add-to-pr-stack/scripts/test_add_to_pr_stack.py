"""Tests for add_to_pr_stack.py — the deterministic script behind the `add-to-pr-stack` skill.

Covers:
- add_to_pr_stack(): recovery re-entry (added_to_stack already true, or stack_link_status already
  resolved), the two "nothing to register" early exits (no parent_work_item, no spec_path), the
  first-task-in-epic form (anchor is None, links with --base), the has-a-dependency form (anchor
  resolved from that task's own context file), and every failure path (missing working_branch/
  base_branch, missing anchor context file, missing anchor working_branch, unreadable/malformed
  spec, and `link` itself failing).
- resolve_context_path(): work-item-id form vs. an existing context-file path.
- write_pending_deliverable(): creates .pending/ and writes the expected slugged filename/content.
- main() CLI wrapper: happy path (prints JSON, exit 0), missing context file, and a failure
  surfaced as `Error: ...` on stderr with a non-zero exit.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).parent
_SKILLS_DIR = SCRIPTS_DIR.parent.parent

# add_to_pr_stack.py itself inserts these at import time, but several tests below import
# dev_team/pipeline_context/get_context_path directly (to seed context files) before ever
# importing add_to_pr_stack, so this module needs the same sys.path setup up front.
sys.path.insert(0, str(_SKILLS_DIR / "workflow-orchestrate" / "scripts"))


def _seed_context(tmp_path, monkeypatch, work_item_id="ADR-1", **kwargs):
    monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
    from dev_team import compute_context_path
    from get_context_path import get_repo_slug
    from pipeline_context import PipelineContext

    path = compute_context_path(work_item_id, get_repo_slug())
    ctx = PipelineContext(work_item_id=work_item_id, **kwargs)
    ctx.save(path)
    return path


def _write_spec(tmp_path, order_with_dependencies: list[tuple[str, str]]) -> Path:
    sections = []
    for task_key, depends_on in order_with_dependencies:
        sections.append(
            f"### [{task_key}: Title](https://example.com/{task_key}) \U0001f916\n\n"
            f"**Depends on:** {depends_on}\n"
        )
    spec_path = tmp_path / "spec.md"
    spec_path.write_text("## Tasks\n\n" + "\n".join(sections), encoding="utf-8")
    return spec_path


# ---------------------------------------------------------------------------
# add_to_pr_stack — recovery re-entry, no `link` call
# ---------------------------------------------------------------------------

class TestAddToPrStackRecoveryReentry:
    def test_already_added_to_stack_returns_linked_without_calling_link(self, tmp_path, monkeypatch):
        # Arrange
        path = _seed_context(tmp_path, monkeypatch, added_to_stack=True)
        from add_to_pr_stack import add_to_pr_stack

        # Act
        with patch("add_to_pr_stack.gh_stack.link") as mock_link:
            result = add_to_pr_stack(path)

        # Assert
        assert result == {"status": "linked"}
        mock_link.assert_not_called()

    def test_already_resolved_not_applicable_returns_it_without_calling_link(self, tmp_path, monkeypatch):
        # Arrange
        path = _seed_context(tmp_path, monkeypatch)
        text = path.read_text(encoding="utf-8")
        text = text.replace("added_to_stack: False", "added_to_stack: False\nstack_link_status: not_applicable")
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack

        # Act
        with patch("add_to_pr_stack.gh_stack.link") as mock_link:
            result = add_to_pr_stack(path)

        # Assert
        assert result == {"status": "not_applicable"}
        mock_link.assert_not_called()


# ---------------------------------------------------------------------------
# add_to_pr_stack — nothing to register: no parent_work_item, or no spec_path
# ---------------------------------------------------------------------------

class TestAddToPrStackNothingToRegister:
    def test_no_parent_work_item_marks_not_applicable_and_leaves_added_to_stack_false(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        path = _seed_context(tmp_path, monkeypatch, spec_path=str(tmp_path / "spec.md"))
        from add_to_pr_stack import add_to_pr_stack
        from pipeline_context import PipelineContext

        # Act
        with patch("add_to_pr_stack.gh_stack.link") as mock_link:
            result = add_to_pr_stack(path)

        # Assert
        assert result == {"status": "not_applicable"}
        mock_link.assert_not_called()
        reloaded = PipelineContext.load(path)
        assert reloaded.added_to_stack is False
        assert reloaded.extra_frontmatter["stack_link_status"] == "not_applicable"

    def test_no_spec_path_marks_not_applicable(self, tmp_path, monkeypatch):
        # Arrange
        path = _seed_context(tmp_path, monkeypatch)
        text = path.read_text(encoding="utf-8").replace(
            "spec_path: \n", "spec_path: \nparent_work_item: ADR-EPIC\n"
        )
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack

        # Act
        with patch("add_to_pr_stack.gh_stack.link") as mock_link:
            result = add_to_pr_stack(path)

        # Assert
        assert result == {"status": "not_applicable"}
        mock_link.assert_not_called()


# ---------------------------------------------------------------------------
# add_to_pr_stack — first task in the epic's stack (anchor is None): links with --base
# ---------------------------------------------------------------------------

class TestAddToPrStackFirstTaskInStack:
    def test_no_dependencies_links_own_branch_with_base(self, tmp_path, monkeypatch):
        # Arrange
        spec_path = _write_spec(tmp_path, [("ADR-1", "— none —")])
        path = _seed_context(
            tmp_path, monkeypatch,
            spec_path=str(spec_path),
        )
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "added_to_stack: False",
            "added_to_stack: False\nparent_work_item: ADR-EPIC\n"
            "working_branch: dev/claude/ADR-1\nbase_branch: feature/ADR-EPIC",
        )
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack
        from pipeline_context import PipelineContext

        # Act
        with patch("add_to_pr_stack.gh_stack.link", return_value=("ok", "Linked")) as mock_link:
            result = add_to_pr_stack(path)

        # Assert
        assert result == {"status": "linked"}
        mock_link.assert_called_once_with("dev/claude/ADR-1", base="feature/ADR-EPIC")
        reloaded = PipelineContext.load(path)
        assert reloaded.added_to_stack is True
        assert reloaded.extra_frontmatter["stack_link_status"] == "linked"

    def test_no_dependencies_missing_base_branch_raises(self, tmp_path, monkeypatch):
        # Arrange
        spec_path = _write_spec(tmp_path, [("ADR-1", "— none —")])
        path = _seed_context(tmp_path, monkeypatch, spec_path=str(spec_path))
        text = path.read_text(encoding="utf-8").replace(
            "added_to_stack: False",
            "added_to_stack: False\nparent_work_item: ADR-EPIC\nworking_branch: dev/claude/ADR-1",
        )
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack, AddToPrStackError

        # Act / Assert
        with patch("add_to_pr_stack.gh_stack.link") as mock_link:
            with pytest.raises(AddToPrStackError, match="base_branch"):
                add_to_pr_stack(path)
        mock_link.assert_not_called()


# ---------------------------------------------------------------------------
# add_to_pr_stack — has a dependency (anchor resolved): links anchor's branch to this task's own
# ---------------------------------------------------------------------------

class TestAddToPrStackHasDependency:
    def test_dependency_links_anchor_branch_to_own_branch(self, tmp_path, monkeypatch):
        # Arrange
        spec_path = _write_spec(tmp_path, [("ADR-1", "— none —"), ("ADR-2", "ADR-1")])
        anchor_path = _seed_context(tmp_path, monkeypatch, work_item_id="ADR-1")
        anchor_text = anchor_path.read_text(encoding="utf-8").replace(
            "added_to_stack: False", "added_to_stack: True\nworking_branch: dev/claude/ADR-1"
        )
        anchor_path.write_text(anchor_text, encoding="utf-8")

        path = _seed_context(tmp_path, monkeypatch, work_item_id="ADR-2", spec_path=str(spec_path))
        text = path.read_text(encoding="utf-8").replace(
            "added_to_stack: False",
            "added_to_stack: False\nparent_work_item: ADR-EPIC\nworking_branch: dev/claude/ADR-2",
        )
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack

        # Act
        with patch("add_to_pr_stack.gh_stack.link", return_value=("ok", "Linked")) as mock_link:
            result = add_to_pr_stack(path)

        # Assert
        assert result == {"status": "linked"}
        mock_link.assert_called_once_with("dev/claude/ADR-1", "dev/claude/ADR-2")

    def test_anchor_context_file_missing_raises(self, tmp_path, monkeypatch):
        # Arrange
        spec_path = _write_spec(tmp_path, [("ADR-1", "— none —"), ("ADR-2", "ADR-1")])
        path = _seed_context(tmp_path, monkeypatch, work_item_id="ADR-2", spec_path=str(spec_path))
        text = path.read_text(encoding="utf-8").replace(
            "added_to_stack: False",
            "added_to_stack: False\nparent_work_item: ADR-EPIC\nworking_branch: dev/claude/ADR-2",
        )
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack, AddToPrStackError

        # Act / Assert
        with patch("add_to_pr_stack.gh_stack.link") as mock_link:
            with pytest.raises(AddToPrStackError, match="ADR-1"):
                add_to_pr_stack(path)
        mock_link.assert_not_called()

    def test_anchor_missing_working_branch_raises(self, tmp_path, monkeypatch):
        # Arrange
        spec_path = _write_spec(tmp_path, [("ADR-1", "— none —"), ("ADR-2", "ADR-1")])
        _seed_context(tmp_path, monkeypatch, work_item_id="ADR-1", added_to_stack=True)
        path = _seed_context(tmp_path, monkeypatch, work_item_id="ADR-2", spec_path=str(spec_path))
        text = path.read_text(encoding="utf-8").replace(
            "added_to_stack: False",
            "added_to_stack: False\nparent_work_item: ADR-EPIC\nworking_branch: dev/claude/ADR-2",
        )
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack, AddToPrStackError

        # Act / Assert
        with patch("add_to_pr_stack.gh_stack.link") as mock_link:
            with pytest.raises(AddToPrStackError, match="working_branch"):
                add_to_pr_stack(path)
        mock_link.assert_not_called()


# ---------------------------------------------------------------------------
# add_to_pr_stack — spec read/parse failures
# ---------------------------------------------------------------------------

class TestAddToPrStackSpecFailures:
    def test_unreadable_spec_file_raises(self, tmp_path, monkeypatch):
        # Arrange
        path = _seed_context(tmp_path, monkeypatch, spec_path=str(tmp_path / "missing.md"))
        text = path.read_text(encoding="utf-8").replace(
            "added_to_stack: False", "added_to_stack: False\nparent_work_item: ADR-EPIC"
        )
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack, AddToPrStackError

        # Act / Assert
        with pytest.raises(AddToPrStackError, match="could not read spec file"):
            add_to_pr_stack(path)

    def test_malformed_spec_raises(self, tmp_path, monkeypatch):
        # Arrange — a dangling `Depends on:` reference (ADR-GHOST is never its own task heading)
        spec_path = _write_spec(tmp_path, [("ADR-99", "ADR-GHOST")])
        path = _seed_context(tmp_path, monkeypatch, work_item_id="ADR-99", spec_path=str(spec_path))
        text = path.read_text(encoding="utf-8").replace(
            "added_to_stack: False", "added_to_stack: False\nparent_work_item: ADR-EPIC"
        )
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack, AddToPrStackError

        # Act / Assert
        with pytest.raises(AddToPrStackError, match="could not compute stack order"):
            add_to_pr_stack(path)


# ---------------------------------------------------------------------------
# add_to_pr_stack — `link` itself fails
# ---------------------------------------------------------------------------

class TestAddToPrStackLinkFails:
    def test_link_error_result_raises_with_detail(self, tmp_path, monkeypatch):
        # Arrange
        spec_path = _write_spec(tmp_path, [("ADR-1", "— none —")])
        path = _seed_context(tmp_path, monkeypatch, spec_path=str(spec_path))
        text = path.read_text(encoding="utf-8").replace(
            "added_to_stack: False",
            "added_to_stack: False\nparent_work_item: ADR-EPIC\n"
            "working_branch: dev/claude/ADR-1\nbase_branch: feature/ADR-EPIC",
        )
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack, AddToPrStackError
        from pipeline_context import PipelineContext

        # Act / Assert
        with patch(
            "add_to_pr_stack.gh_stack.link",
            return_value=("error", "PR #42 belongs to a different stack"),
        ):
            with pytest.raises(AddToPrStackError, match="PR #42 belongs to a different stack"):
                add_to_pr_stack(path)

        reloaded = PipelineContext.load(path)
        assert reloaded.added_to_stack is False


# ---------------------------------------------------------------------------
# resolve_context_path
# ---------------------------------------------------------------------------

class TestResolveContextPath:
    def test_existing_file_path_returned_as_is(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        existing = tmp_path / "ADR-1.md"
        existing.write_text("---\n---\n", encoding="utf-8")
        from add_to_pr_stack import resolve_context_path

        # Act
        result = resolve_context_path(str(existing))

        # Assert
        assert result == existing

    def test_work_item_id_computes_context_path(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from add_to_pr_stack import resolve_context_path
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug

        # Act
        result = resolve_context_path("ADR-1")

        # Assert
        assert result == compute_context_path("ADR-1", get_repo_slug())


# ---------------------------------------------------------------------------
# write_pending_deliverable
# ---------------------------------------------------------------------------

class TestWritePendingDeliverable:
    def test_writes_slugged_file_under_pending_dir(self, tmp_path):
        # Arrange
        context_path = tmp_path / "ADR-1.md"
        from add_to_pr_stack import write_pending_deliverable

        # Act
        write_pending_deliverable(context_path, "Stack Link Result", '{"status": "linked"}')

        # Assert
        expected = tmp_path / ".pending" / "ADR-1__Stack_Link_Result.md"
        assert expected.read_text(encoding="utf-8") == '{"status": "linked"}'


# ---------------------------------------------------------------------------
# main() CLI wrapper
# ---------------------------------------------------------------------------

class TestMainCliWrapper:
    def test_main_happy_path_prints_json_and_writes_pending_deliverable(
        self, tmp_path, monkeypatch, capsys
    ):
        """In-process (not subprocess) so `gh_stack.link` can be mocked — a real subprocess call
        would need actual `gh` credentials and would shell out for real."""
        # Arrange
        spec_path = _write_spec(tmp_path, [("ADR-1", "— none —")])
        path = _seed_context(tmp_path, monkeypatch, spec_path=str(spec_path))
        text = path.read_text(encoding="utf-8").replace(
            "added_to_stack: False",
            "added_to_stack: False\nparent_work_item: ADR-EPIC\n"
            "working_branch: dev/claude/ADR-1\nbase_branch: feature/ADR-EPIC",
        )
        path.write_text(text, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["add_to_pr_stack.py", "ADR-1"])
        import add_to_pr_stack

        # Act
        with patch("add_to_pr_stack.gh_stack.link", return_value=("ok", "Linked")):
            add_to_pr_stack.main()

        # Assert
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"status": "linked"}
        pending = path.parent / ".pending" / "ADR-1__Stack_Link_Result.md"
        assert json.loads(pending.read_text(encoding="utf-8")) == {"status": "linked"}

    def test_main_missing_context_file_prints_error_and_exits_nonzero(self, tmp_path, monkeypatch):
        # Arrange
        env = {
            **__import__("os").environ,
            "DEV_TEAM_STATE_DIR": str(tmp_path),
            "GIT_REMOTE_URL_OVERRIDE": "https://github.com/example/repo.git",
        }

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "add_to_pr_stack.py"), "ADR-DOES-NOT-EXIST"],
            capture_output=True, text=True, timeout=15, env=env,
        )

        # Assert
        assert result.returncode != 0
        assert "Error: context file not found" in result.stderr
