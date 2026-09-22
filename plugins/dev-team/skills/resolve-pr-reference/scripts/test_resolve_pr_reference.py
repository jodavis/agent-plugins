"""Tests for resolve_pr_reference.py — resolve_pr_reference() resolves a PR reference (a bare
number/`#123`, a full GitHub PR URL, or a work-item ID) to exactly one `owner/repo#number`, or a
structured not_found/ambiguous/access_denied failure.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def expect_gh_pr_view_succeeds(state: str = "OPEN") -> dict:
    return {"returncode": 0, "stdout": json.dumps({"number": 1, "url": "x", "state": state}), "stderr": ""}


def make_fake_run(handlers):
    """Build a subprocess.run side_effect that dispatches on a command-prefix -> handler map.
    Each handler is a callable(cmd, **kwargs) -> MagicMock, or a dict of
    {returncode, stdout, stderr} to wrap directly."""

    def fake_run(cmd, **kwargs):
        for prefix, handler in handlers.items():
            if tuple(cmd[: len(prefix)]) == prefix:
                if callable(handler):
                    return handler(cmd, **kwargs)
                return MagicMock(
                    returncode=handler.get("returncode", 0),
                    stdout=handler.get("stdout", ""),
                    stderr=handler.get("stderr", ""),
                )
        raise AssertionError(f"unexpected command: {cmd}")

    return fake_run


JIRA_WORK_TRACKING = {
    "jira": {"issue-key-pattern": "AIP-\\d+", "recognize-patterns": ["Task \\d+", "Jira \\d+"]},
    "github": {"issue-key-pattern": "Issue-\\d+", "recognize-patterns": ["#\\d+", "Issue \\d+"]},
}


# ---------------------------------------------------------------------------
# Full GitHub PR URL — resolves independent of the current repo
# ---------------------------------------------------------------------------

class TestResolvePrReferenceFullUrl:
    def test_resolve_pr_reference_full_github_pr_url_resolves_independent_of_current_repo(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/other/repo.git")
        from resolve_pr_reference import resolve_pr_reference

        fake_run = make_fake_run({("gh", "pr", "view"): expect_gh_pr_view_succeeds()})

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve_pr_reference(" https://github.com/acme/widget/pull/42 ")

        # Assert
        assert result == {
            "status": "resolved",
            "owner": "acme",
            "repo": "widget",
            "number": 42,
            "pr_url": "https://github.com/acme/widget/pull/42",
            "source": "url",
        }


# ---------------------------------------------------------------------------
# Bare PR number (or #123) — resolves against the current repo's origin
# ---------------------------------------------------------------------------

class TestResolvePrReferenceBareNumber:
    @pytest.mark.parametrize("ref", ["42", "#42"], ids=["bare_number", "hash_prefixed_number"])
    def test_resolve_pr_reference_bare_number_resolves_against_current_repo_origin(
        self, tmp_path, monkeypatch, ref
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        from resolve_pr_reference import resolve_pr_reference

        fake_run = make_fake_run({("gh", "pr", "view"): expect_gh_pr_view_succeeds()})

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve_pr_reference(ref)

        # Assert
        assert result == {
            "status": "resolved",
            "owner": "acme",
            "repo": "widget",
            "number": 42,
            "pr_url": "https://github.com/acme/widget/pull/42",
            "source": "number",
        }

    def test_resolve_pr_reference_bare_number_unparseable_current_repo_slug_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://gitlab.com/group/subgroup/repo.git")
        from resolve_pr_reference import resolve_pr_reference

        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve_pr_reference("42")

        # Assert
        assert result["status"] == "not_found"
        assert "owner/repo" in result["detail"]
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# A ref matching none of the recognized shapes
# ---------------------------------------------------------------------------

class TestResolvePrReferenceUnrecognizedShape:
    @pytest.mark.parametrize(
        "work_tracking",
        [
            pytest.param({}, id="no_providers_configured"),
            pytest.param(JIRA_WORK_TRACKING, id="providers_configured_but_no_match"),
        ],
    )
    def test_resolve_pr_reference_unrecognized_ref_returns_not_found_with_distinct_detail(
        self, tmp_path, monkeypatch, work_tracking
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": work_tracking}
        )
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("not-a-recognized-ref!!")

        # Assert
        assert result["status"] == "not_found"
        assert "did not match any recognized format" in result["detail"]
        mock_run.assert_not_called()

    def test_resolve_pr_reference_empty_ref_returns_not_found(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        from resolve_pr_reference import resolve_pr_reference

        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve_pr_reference("   ")

        # Assert
        assert result == {"status": "not_found", "detail": "ref is empty; did not match any recognized format"}
        mock_run.assert_not_called()

    def test_resolve_pr_reference_project_configuration_unreadable_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        def raise_runtime_error():
            raise RuntimeError("could not locate repo root")

        monkeypatch.setattr(resolve_pr_reference, "build_merged_config", raise_runtime_error)
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("AIP-18")

        # Assert
        assert result["status"] == "not_found"
        assert "project configuration could not be loaded" in result["detail"]
        mock_run.assert_not_called()

    def test_resolve_pr_reference_malformed_provider_regex_pattern_is_skipped_not_raised(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        broken_work_tracking = {"jira": {"issue-key-pattern": "AIP-[", "recognize-patterns": []}}
        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": broken_work_tracking}
        )
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("AIP-18")

        # Assert
        assert result["status"] == "not_found"
        assert "did not match any recognized format" in result["detail"]
        mock_run.assert_not_called()

    def test_resolve_pr_reference_work_item_provider_with_no_dispatch_logic_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        gitlab_work_tracking = {"gitlab": {"issue-key-pattern": "GL-\\d+", "recognize-patterns": []}}
        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": gitlab_work_tracking}
        )
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("GL-9")

        # Assert
        assert result["status"] == "not_found"
        assert "gitlab" in result["detail"]
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Work-item ID with an existing use-context-file context file whose pr_url is set
# ---------------------------------------------------------------------------

class TestResolvePrReferenceWorkItemContextFile:
    def test_resolve_pr_reference_work_item_with_context_file_pr_url_resolves_without_querying_provider(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        path = compute_context_path("AIP-18", get_repo_slug())
        PipelineContext(
            work_item_id="AIP-18", pr_url="https://github.com/acme/widget/pull/57"
        ).save(path)
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("AIP-18")

        # Assert
        assert result == {
            "status": "resolved",
            "owner": "acme",
            "repo": "widget",
            "number": 57,
            "pr_url": "https://github.com/acme/widget/pull/57",
            "source": "work-item-context-file",
        }
        mock_run.assert_not_called()

    def test_resolve_pr_reference_context_file_malformed_pr_url_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        path = compute_context_path("AIP-18", get_repo_slug())
        PipelineContext(work_item_id="AIP-18", pr_url="not-a-url").save(path)
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("AIP-18")

        # Assert
        assert result["status"] == "not_found"
        assert "pr_url" in result["detail"]
        mock_run.assert_not_called()

    def test_resolve_pr_reference_context_file_exists_with_empty_pr_url_falls_through_to_provider(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        path = compute_context_path("AIP-18", get_repo_slug())
        PipelineContext(work_item_id="AIP-18", pr_url="").save(path)
        jira_links = [{"object": {"url": "https://github.com/acme/widget/pull/7"}}]

        # Act
        with patch("subprocess.run", MagicMock()):
            result = resolve("AIP-18", jira_links=jira_links)

        # Assert
        assert result["status"] == "resolved"
        assert result["source"] == "work-item-jira-remote-link"
        assert result["number"] == 7


# ---------------------------------------------------------------------------
# Jira work-item path — remote links
# ---------------------------------------------------------------------------

class TestResolvePrReferenceJiraRemoteLinks:
    def test_resolve_pr_reference_jira_single_remote_link_resolves_without_github_search(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        jira_links = [{"object": {"url": "https://github.com/acme/widget/pull/7"}}]
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("AIP-18", jira_links=jira_links)

        # Assert
        assert result == {
            "status": "resolved",
            "owner": "acme",
            "repo": "widget",
            "number": 7,
            "pr_url": "https://github.com/acme/widget/pull/7",
            "source": "work-item-jira-remote-link",
        }
        mock_run.assert_not_called()

    def test_resolve_pr_reference_jira_remote_link_url_field_at_top_level_also_matches(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        jira_links = [{"url": "https://github.com/acme/widget/pull/7"}]
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("AIP-18", jira_links=jira_links)

        # Assert
        assert result["status"] == "resolved"
        assert result["number"] == 7

    def test_resolve_pr_reference_jira_remote_links_non_pr_urls_are_ignored(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        jira_links = [
            {"object": {"url": "https://example.atlassian.net/wiki/page"}},
            {"not-a-dict": True},
            "not-even-a-dict",
        ]
        fake_run = make_fake_run(
            {
                ("gh", "search", "prs"): {"returncode": 0, "stdout": json.dumps([{"number": 9}])},
                ("gh", "pr", "list"): {"returncode": 0, "stdout": json.dumps([])},
            }
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("AIP-18", jira_links=jira_links)

        # Assert
        assert result["status"] == "resolved"
        assert result["source"] == "work-item-jira-github-search"
        assert result["number"] == 9

    def test_resolve_pr_reference_jira_multiple_remote_links_returns_ambiguous_without_fallback(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        jira_links = [
            {"object": {"url": "https://github.com/acme/widget/pull/7"}},
            {"object": {"url": "https://github.com/acme/widget/pull/8"}},
        ]
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("AIP-18", jira_links=jira_links)

        # Assert
        assert result["status"] == "ambiguous"
        assert "7" in result["detail"] and "8" in result["detail"]
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Jira work-item path — GitHub-search fallback (remote links empty)
# ---------------------------------------------------------------------------

class TestResolvePrReferenceJiraGithubSearchFallback:
    def test_resolve_pr_reference_jira_no_remote_links_falls_back_to_github_search_title_match(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        fake_run = make_fake_run(
            {
                ("gh", "search", "prs"): {"returncode": 0, "stdout": json.dumps([{"number": 9}])},
                ("gh", "pr", "list"): {"returncode": 0, "stdout": json.dumps([])},
            }
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("AIP-18", jira_links=[])

        # Assert
        assert result == {
            "status": "resolved",
            "owner": "acme",
            "repo": "widget",
            "number": 9,
            "pr_url": "https://github.com/acme/widget/pull/9",
            "source": "work-item-jira-github-search",
        }

    def test_resolve_pr_reference_jira_no_remote_links_falls_back_to_github_search_branch_name_match(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        fake_run = make_fake_run(
            {
                ("gh", "search", "prs"): {"returncode": 0, "stdout": json.dumps([])},
                ("gh", "pr", "list"): {
                    "returncode": 0,
                    "stdout": json.dumps([{"number": 12, "headRefName": "dev/claude/AIP-18"}]),
                },
            }
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("AIP-18", jira_links=None)

        # Assert
        assert result["status"] == "resolved"
        assert result["number"] == 12
        assert result["source"] == "work-item-jira-github-search"

    def test_resolve_pr_reference_jira_fallback_dedupes_same_pr_found_by_both_searches(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        fake_run = make_fake_run(
            {
                ("gh", "search", "prs"): {"returncode": 0, "stdout": json.dumps([{"number": 9}])},
                ("gh", "pr", "list"): {
                    "returncode": 0,
                    "stdout": json.dumps([{"number": 9, "headRefName": "dev/claude/AIP-18"}]),
                },
            }
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("AIP-18", jira_links=[])

        # Assert
        assert result["status"] == "resolved"
        assert result["number"] == 9

    def test_resolve_pr_reference_jira_fallback_finds_two_different_prs_returns_ambiguous(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        fake_run = make_fake_run(
            {
                ("gh", "search", "prs"): {"returncode": 0, "stdout": json.dumps([{"number": 9}])},
                ("gh", "pr", "list"): {
                    "returncode": 0,
                    "stdout": json.dumps([{"number": 11, "headRefName": "dev/claude/AIP-18"}]),
                },
            }
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("AIP-18", jira_links=[])

        # Assert
        assert result["status"] == "ambiguous"
        assert "9" in result["detail"] and "11" in result["detail"]

    def test_resolve_pr_reference_jira_fallback_finds_nothing_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        fake_run = make_fake_run(
            {
                ("gh", "search", "prs"): {"returncode": 0, "stdout": json.dumps([])},
                ("gh", "pr", "list"): {"returncode": 0, "stdout": json.dumps([])},
            }
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("AIP-18", jira_links=[])

        # Assert
        assert result["status"] == "not_found"
        assert "AIP-18" in result["detail"]

    def test_resolve_pr_reference_jira_fallback_gh_calls_fail_or_return_invalid_json_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        fake_run = make_fake_run(
            {
                ("gh", "search", "prs"): {"returncode": 1, "stdout": "", "stderr": "rate limited"},
                ("gh", "pr", "list"): {"returncode": 0, "stdout": "not json"},
            }
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("AIP-18", jira_links=[])

        # Assert
        assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# GitHub work-item path — getLinkedPullRequests (gh api graphql)
# ---------------------------------------------------------------------------

class TestResolvePrReferenceGithubLinkedPr:
    def test_resolve_pr_reference_github_work_item_single_linked_pr_resolves(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        graphql_response = {
            "data": {
                "repository": {
                    "issue": {"closedByPullRequestsReferences": {"nodes": [{"number": 5}]}}
                }
            }
        }
        fake_run = make_fake_run(
            {("gh", "api", "graphql"): {"returncode": 0, "stdout": json.dumps(graphql_response)}}
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("Issue-42")

        # Assert
        assert result == {
            "status": "resolved",
            "owner": "acme",
            "repo": "widget",
            "number": 5,
            "pr_url": "https://github.com/acme/widget/pull/5",
            "source": "work-item-github-linked-pr",
        }

    def test_resolve_pr_reference_github_work_item_zero_linked_prs_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        graphql_response = {
            "data": {
                "repository": {"issue": {"closedByPullRequestsReferences": {"nodes": []}}}
            }
        }
        fake_run = make_fake_run(
            {("gh", "api", "graphql"): {"returncode": 0, "stdout": json.dumps(graphql_response)}}
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("Issue-42")

        # Assert
        assert result["status"] == "not_found"

    def test_resolve_pr_reference_github_work_item_multiple_linked_prs_returns_ambiguous(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        graphql_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {"nodes": [{"number": 5}, {"number": 6}]}
                    }
                }
            }
        }
        fake_run = make_fake_run(
            {("gh", "api", "graphql"): {"returncode": 0, "stdout": json.dumps(graphql_response)}}
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("Issue-42")

        # Assert
        assert result["status"] == "ambiguous"
        assert "5" in result["detail"] and "6" in result["detail"]

    def test_resolve_pr_reference_github_work_item_graphql_call_fails_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        fake_run = make_fake_run(
            {("gh", "api", "graphql"): {"returncode": 1, "stdout": "", "stderr": "boom"}}
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("Issue-42")

        # Assert
        assert result["status"] == "not_found"

    def test_resolve_pr_reference_github_work_item_graphql_returns_invalid_json_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        fake_run = make_fake_run(
            {("gh", "api", "graphql"): {"returncode": 0, "stdout": "not json"}}
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve("Issue-42")

        # Assert
        assert result["status"] == "not_found"

    def test_resolve_pr_reference_github_work_item_ref_with_no_digits_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        no_digit_work_tracking = {"github": {"issue-key-pattern": "gh-issue", "recognize-patterns": []}}
        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": no_digit_work_tracking}
        )
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("gh-issue")

        # Assert
        assert result["status"] == "not_found"
        assert "numeric issue number" in result["detail"]


# ---------------------------------------------------------------------------
# Work item — unparseable repo slug for work-item resolution (not just bare number)
# ---------------------------------------------------------------------------

class TestResolvePrReferenceWorkItemUnparseableRepoSlug:
    def test_resolve_pr_reference_work_item_unparseable_current_repo_slug_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://gitlab.com/group/subgroup/repo.git")
        import resolve_pr_reference
        from resolve_pr_reference import resolve_pr_reference as resolve

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = resolve("AIP-18", jira_links=[])

        # Assert
        assert result["status"] == "not_found"
        assert "owner/repo" in result["detail"]
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# gh pr view existence/access checks (shared by url and number paths)
# ---------------------------------------------------------------------------

class TestResolvePrReferenceGhPrViewOutcomes:
    def test_resolve_pr_reference_pr_does_not_exist_returns_not_found_with_reason(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        from resolve_pr_reference import resolve_pr_reference

        fake_run = make_fake_run(
            {
                ("gh", "pr", "view"): {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "GraphQL: Could not resolve to a PullRequest with the number of 42.",
                }
            }
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve_pr_reference("https://github.com/acme/widget/pull/42")

        # Assert
        assert result["status"] == "not_found"
        assert "42" in result["detail"]

    def test_resolve_pr_reference_pr_not_accessible_returns_access_denied_with_reason(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        from resolve_pr_reference import resolve_pr_reference

        fake_run = make_fake_run(
            {
                ("gh", "pr", "view"): {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "HTTP 403: Resource not accessible by integration",
                }
            }
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve_pr_reference("https://github.com/acme/widget/pull/42")

        # Assert
        assert result["status"] == "access_denied"
        assert "403" in result["detail"]

    def test_resolve_pr_reference_gh_pr_view_invalid_json_output_returns_not_found(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        from resolve_pr_reference import resolve_pr_reference

        fake_run = make_fake_run(
            {("gh", "pr", "view"): {"returncode": 0, "stdout": "not json", "stderr": ""}}
        )

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = resolve_pr_reference("https://github.com/acme/widget/pull/42")

        # Assert
        assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# main() — CLI wrapper
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_resolved_ref_prints_json_to_stdout_and_exits_zero(
        self, tmp_path, monkeypatch, capsys
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import main

        monkeypatch.setattr(sys, "argv", ["resolve_pr_reference.py", "https://github.com/acme/widget/pull/42"])
        fake_run = make_fake_run({("gh", "pr", "view"): expect_gh_pr_view_succeeds()})

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            main()

        # Assert
        captured = json.loads(capsys.readouterr().out)
        assert captured["status"] == "resolved"
        assert captured["number"] == 42

    def test_main_with_jira_links_flag_passes_parsed_json_through(
        self, tmp_path, monkeypatch, capsys
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        import resolve_pr_reference
        from resolve_pr_reference import main

        monkeypatch.setattr(
            resolve_pr_reference, "build_merged_config", lambda: {"work-tracking": JIRA_WORK_TRACKING}
        )
        jira_links_json = json.dumps([{"object": {"url": "https://github.com/acme/widget/pull/7"}}])
        monkeypatch.setattr(
            sys, "argv", ["resolve_pr_reference.py", "AIP-18", "--jira-links", jira_links_json]
        )
        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            main()

        # Assert
        captured = json.loads(capsys.readouterr().out)
        assert captured["status"] == "resolved"
        assert captured["number"] == 7
        assert captured["source"] == "work-item-jira-remote-link"

    def test_main_invalid_jira_links_json_exits_nonzero_with_error_message(
        self, tmp_path, monkeypatch, capsys
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/acme/widget.git")
        from resolve_pr_reference import main

        monkeypatch.setattr(
            sys, "argv", ["resolve_pr_reference.py", "AIP-18", "--jira-links", "not-json"]
        )

        # Act / Assert
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code != 0
        assert "Error" in capsys.readouterr().err
