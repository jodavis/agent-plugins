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
# add_to_pr_stack — first task in the epic's stack (anchor is None): nothing to link yet (#256)
# ---------------------------------------------------------------------------

class TestAddToPrStackFirstTaskInStack:
    def test_no_dependencies_marks_not_applicable_without_calling_link(self, tmp_path, monkeypatch):
        """An epic's first task (no declared dependency) is based directly on the feature
        branch — there's no stack relationship to register yet, and `gh stack link` structurally
        requires >=2 positional args anyway, so this must not attempt to call it at all (#256)."""
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
        with patch("add_to_pr_stack.gh_stack.link") as mock_link:
            result = add_to_pr_stack(path)

        # Assert
        assert result == {"status": "not_applicable"}
        mock_link.assert_not_called()
        reloaded = PipelineContext.load(path)
        assert reloaded.added_to_stack is False
        assert reloaded.extra_frontmatter["stack_link_status"] == "not_applicable"


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

        # Act — _resolve_real_stack_chain mocked to its degraded-fallback shape (single anchor,
        # no earlier members found) so this test doesn't need a real `gh pr list` call.
        with patch("add_to_pr_stack._resolve_real_stack_chain", return_value=["dev/claude/ADR-1"]):
            with patch("add_to_pr_stack.gh_stack.link", return_value=("ok", "Linked")) as mock_link:
                result = add_to_pr_stack(path)

        # Assert
        assert result == {"status": "linked"}
        mock_link.assert_called_once_with("dev/claude/ADR-1", "dev/claude/ADR-2")

    def test_dependency_with_multi_level_chain_passes_every_earlier_member(self, tmp_path, monkeypatch):
        """Regression (#273): when the anchor is itself mid-stack, every real earlier member
        below it must also be passed to `link`, or `gh stack link` refuses the update rather
        than risk dropping them."""
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

        # Act — the anchor's real chain (as resolved from GitHub) has an earlier member below it
        with patch(
            "add_to_pr_stack._resolve_real_stack_chain",
            return_value=["feature/ADR-EPIC-doc", "dev/claude/ADR-1"],
        ):
            with patch("add_to_pr_stack.gh_stack.link", return_value=("ok", "Linked")) as mock_link:
                result = add_to_pr_stack(path)

        # Assert
        assert result == {"status": "linked"}
        mock_link.assert_called_once_with(
            "feature/ADR-EPIC-doc", "dev/claude/ADR-1", "dev/claude/ADR-2"
        )

    def test_own_base_branch_preferred_over_stale_spec_derived_anchor(self, tmp_path, monkeypatch):
        """Regression (#276): a mid-implementation fast-forward corrects this task's own
        base_branch to the real anchor, even when the spec's Depends-on line (and therefore the
        spec-derived anchor task's own working_branch) is left stale."""
        # Arrange — spec still says ADR-2 depends only on ADR-1, but this task's own base_branch
        # was corrected to a later dependency's branch after a real mid-implementation rebase.
        spec_path = _write_spec(tmp_path, [("ADR-1", "— none —"), ("ADR-2", "ADR-1")])
        anchor_path = _seed_context(tmp_path, monkeypatch, work_item_id="ADR-1")
        anchor_text = anchor_path.read_text(encoding="utf-8").replace(
            "added_to_stack: False", "added_to_stack: True\nworking_branch: dev/claude/ADR-1"
        )
        anchor_path.write_text(anchor_text, encoding="utf-8")

        path = _seed_context(tmp_path, monkeypatch, work_item_id="ADR-2", spec_path=str(spec_path))
        text = path.read_text(encoding="utf-8").replace(
            "added_to_stack: False",
            "added_to_stack: False\nparent_work_item: ADR-EPIC\nworking_branch: dev/claude/ADR-2\n"
            "base_branch: dev/claude/ADR-3",
        )
        path.write_text(text, encoding="utf-8")
        from add_to_pr_stack import add_to_pr_stack

        # Act
        with patch(
            "add_to_pr_stack._resolve_real_stack_chain", return_value=["dev/claude/ADR-3"]
        ) as mock_resolve:
            with patch("add_to_pr_stack.gh_stack.link", return_value=("ok", "Linked")) as mock_link:
                result = add_to_pr_stack(path)

        # Assert
        assert result == {"status": "linked"}
        mock_resolve.assert_called_once_with("dev/claude/ADR-3")
        mock_link.assert_called_once_with("dev/claude/ADR-3", "dev/claude/ADR-2")

    def test_anchor_context_file_missing_marks_not_applicable(self, tmp_path, monkeypatch):
        """The anchor dependency was completed outside the pipeline (e.g. a human-owned task on
        the shared feature branch) and has no context file — nothing to link onto (#271)."""
        # Arrange
        spec_path = _write_spec(tmp_path, [("ADR-1", "— none —"), ("ADR-2", "ADR-1")])
        path = _seed_context(tmp_path, monkeypatch, work_item_id="ADR-2", spec_path=str(spec_path))
        text = path.read_text(encoding="utf-8").replace(
            "added_to_stack: False",
            "added_to_stack: False\nparent_work_item: ADR-EPIC\nworking_branch: dev/claude/ADR-2",
        )
        path.write_text(text, encoding="utf-8")
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
        from add_to_pr_stack import add_to_pr_stack, AddToPrStackError
        from pipeline_context import PipelineContext

        # Act / Assert
        with patch("add_to_pr_stack._resolve_real_stack_chain", return_value=["dev/claude/ADR-1"]):
            with patch(
                "add_to_pr_stack.gh_stack.link",
                return_value=("error", "PR #42 belongs to a different stack"),
            ):
                with pytest.raises(AddToPrStackError, match="PR #42 belongs to a different stack"):
                    add_to_pr_stack(path)

        reloaded = PipelineContext.load(path)
        assert reloaded.added_to_stack is False


# ---------------------------------------------------------------------------
# _resolve_real_stack_chain
# ---------------------------------------------------------------------------

def _gh_pr_list_result(prs: list[dict]) -> "subprocess.CompletedProcess":
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(prs), stderr="")


class TestResolveRealStackChain:
    def test_single_member_chain_stops_at_branch_with_no_pr(self, monkeypatch):
        """anchor_branch's own PR bases off the feature branch, which has no PR of its own —
        the chain is just [anchor_branch]."""
        from add_to_pr_stack import _resolve_real_stack_chain

        calls = [
            _gh_pr_list_result([{"baseRefName": "feature/ADR-EPIC"}]),  # anchor's own PR
            _gh_pr_list_result([]),  # feature branch has no PR of its own
        ]
        with patch("subprocess.run", side_effect=calls):
            result = _resolve_real_stack_chain("dev/claude/ADR-1")

        assert result == ["dev/claude/ADR-1"]

    def test_multi_level_chain_resolved_bottom_to_top(self, monkeypatch):
        """anchor_branch (ADR-2) bases off ADR-1, which itself has its own open PR based off
        the feature branch — both real members must be returned, bottom-to-top."""
        from add_to_pr_stack import _resolve_real_stack_chain

        calls = [
            _gh_pr_list_result([{"baseRefName": "dev/claude/ADR-1"}]),  # ADR-2's own PR
            _gh_pr_list_result([{"baseRefName": "feature/ADR-EPIC"}]),  # ADR-1's own PR
            _gh_pr_list_result([]),  # feature branch has no PR of its own
        ]
        with patch("subprocess.run", side_effect=calls):
            result = _resolve_real_stack_chain("dev/claude/ADR-2")

        assert result == ["dev/claude/ADR-1", "dev/claude/ADR-2"]

    def test_falls_back_to_single_anchor_when_gh_unavailable(self, monkeypatch):
        from add_to_pr_stack import _resolve_real_stack_chain

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _resolve_real_stack_chain("dev/claude/ADR-1")

        assert result == ["dev/claude/ADR-1"]

    def test_falls_back_to_single_anchor_on_nonzero_exit(self, monkeypatch):
        from add_to_pr_stack import _resolve_real_stack_chain

        failure = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="not authenticated")
        with patch("subprocess.run", return_value=failure):
            result = _resolve_real_stack_chain("dev/claude/ADR-1")

        assert result == ["dev/claude/ADR-1"]

    def test_falls_back_to_single_anchor_when_anchor_itself_has_no_open_pr(self, monkeypatch):
        """Degenerate/unexpected case: anchor_branch's own PR lookup comes up empty. Still
        returns the anchor alone rather than an empty chain."""
        from add_to_pr_stack import _resolve_real_stack_chain

        with patch("subprocess.run", return_value=_gh_pr_list_result([])):
            result = _resolve_real_stack_chain("dev/claude/ADR-1")

        assert result == ["dev/claude/ADR-1"]


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
        monkeypatch.setattr(sys, "argv", ["add_to_pr_stack.py", "ADR-2"])
        import add_to_pr_stack

        # Act
        with patch("add_to_pr_stack._resolve_real_stack_chain", return_value=["dev/claude/ADR-1"]):
            with patch("add_to_pr_stack.gh_stack.link", return_value=("ok", "Linked")):
                add_to_pr_stack.main()

        # Assert
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"status": "linked"}
        pending = path.parent / ".pending" / "ADR-2__Stack_Link_Result.md"
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
