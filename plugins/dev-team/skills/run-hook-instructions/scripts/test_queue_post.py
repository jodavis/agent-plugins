"""Tests for queue_post.py — writes one pending-post YAML record (`target`, `channel`,
`content`, `event_context`, `created_at`) to `<state-dir>/<repo-slug>/pending-posts/<id>.yaml`,
reading `content` from a `--content-file` path rather than accepting it inline or via stdin, so
arbitrary comment text never passes through a shell command string.

Covers:
- Record shape: all 5 fields present, correctly valued, and parseable back via
  `merge_config.parse_yaml` (the repo's only existing YAML reader) — including the literal
  block-scalar shape for `content`
- The `--content-file` contract: content is read from the given file, never accepted inline;
  a missing/unreadable file raises `ValueError` instead of letting a raw `OSError` propagate
- `channel` validation: each of the 4 valid values is accepted; anything else raises
  `ValueError`
- `<id>` uniqueness across many rapid invocations (no locking — structural uniqueness only)
- `DEV_TEAM_STATE_DIR` override actually redirects output away from the real home directory
- `main()` CLI wrapper: the happy path, and both documented `Error: ...` failure modes
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent
_GET_PROJECT_CONFIGURATION_SCRIPTS = (
    SCRIPTS_DIR.parent.parent / "get-project-configuration" / "scripts"
)
sys.path.insert(0, str(_GET_PROJECT_CONFIGURATION_SCRIPTS))
from merge_config import parse_yaml  # noqa: E402


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    """Common env seams every test needs: an isolated state dir and a fixed repo slug, so tests
    never write into a real machine's `~/.dev-team/`."""
    monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
    return tmp_path


def _write_content_file(tmp_path: Path, text: str) -> Path:
    content_path = tmp_path / "content.txt"
    content_path.write_text(text, encoding="utf-8")
    return content_path


# ---------------------------------------------------------------------------
# queue_post — record shape
# ---------------------------------------------------------------------------

class TestQueuePostRecordShape:
    def test_queue_post_writes_yaml_record_with_all_five_expected_fields(self, tmp_path):
        # Arrange
        from queue_post import queue_post

        content_path = _write_content_file(tmp_path, "Build passed.\nAll tests green.\n")

        # Act
        record_path = queue_post(
            target="ADR-400",
            channel="jira-comment",
            content_file=str(content_path),
            event_context="after-implement",
        )

        # Assert
        record = parse_yaml(record_path.read_text(encoding="utf-8"), record_path)
        assert record["target"] == "ADR-400"
        assert record["channel"] == "jira-comment"
        assert record["content"] == "Build passed.\nAll tests green.\n"
        assert record["event_context"] == "after-implement"
        assert isinstance(record["created_at"], str) and record["created_at"] != ""

    def test_queue_post_writes_record_under_pending_posts_dir_for_repo_slug(self, tmp_path):
        # Arrange
        from queue_post import queue_post

        content_path = _write_content_file(tmp_path, "Hello.\n")

        # Act
        record_path = queue_post(
            target="ADR-400",
            channel="pr-comment",
            content_file=str(content_path),
            event_context="after-create-pr",
        )

        # Assert
        expected_dir = tmp_path / "example" / "repo" / "pending-posts"
        assert record_path.parent == expected_dir
        assert record_path.suffix == ".yaml"
        assert record_path.is_file()

    def test_queue_post_record_round_trips_special_characters_in_scalar_fields(self, tmp_path):
        # Arrange
        from queue_post import queue_post

        content_path = _write_content_file(tmp_path, "line one\nline two\n")
        target = 'weird "target" value with \\ backslash and: a colon'

        # Act
        record_path = queue_post(
            target=target,
            channel="github-issue-comment",
            content_file=str(content_path),
            event_context="after-review",
        )

        # Assert
        record = parse_yaml(record_path.read_text(encoding="utf-8"), record_path)
        assert record["target"] == target


# ---------------------------------------------------------------------------
# queue_post — content-file contract
# ---------------------------------------------------------------------------

class TestQueuePostContentFileContract:
    def test_queue_post_reads_content_from_content_file_contents(self, tmp_path):
        # Arrange
        from queue_post import queue_post

        content_path = _write_content_file(tmp_path, "Multi-line\nstatus update\nwith detail.\n")

        # Act
        record_path = queue_post(
            target="ADR-400",
            channel="jira-description",
            content_file=str(content_path),
            event_context="before-implement",
        )

        # Assert
        record = parse_yaml(record_path.read_text(encoding="utf-8"), record_path)
        assert record["content"] == "Multi-line\nstatus update\nwith detail.\n"

    def test_queue_post_raises_value_error_when_content_file_does_not_exist(self, tmp_path):
        # Arrange
        from queue_post import queue_post

        missing_path = tmp_path / "does-not-exist.txt"

        # Act / Assert
        with pytest.raises(ValueError, match="does-not-exist.txt"):
            queue_post(
                target="ADR-400",
                channel="jira-comment",
                content_file=str(missing_path),
                event_context="after-implement",
            )


# ---------------------------------------------------------------------------
# queue_post — channel validation
# ---------------------------------------------------------------------------

class TestQueuePostChannelValidation:
    @pytest.mark.parametrize(
        "channel",
        ["jira-comment", "jira-description", "github-issue-comment", "pr-comment"],
    )
    def test_queue_post_accepts_each_valid_channel(self, tmp_path, channel):
        # Arrange
        from queue_post import queue_post

        content_path = _write_content_file(tmp_path, "content\n")

        # Act
        record_path = queue_post(
            target="ADR-400",
            channel=channel,
            content_file=str(content_path),
            event_context="after-implement",
        )

        # Assert
        record = parse_yaml(record_path.read_text(encoding="utf-8"), record_path)
        assert record["channel"] == channel

    def test_queue_post_raises_value_error_for_invalid_channel(self, tmp_path):
        # Arrange
        from queue_post import queue_post

        content_path = _write_content_file(tmp_path, "content\n")

        # Act / Assert
        with pytest.raises(ValueError, match="invalid channel"):
            queue_post(
                target="ADR-400",
                channel="slack-message",
                content_file=str(content_path),
                event_context="after-implement",
            )


# ---------------------------------------------------------------------------
# queue_post — id uniqueness under concurrent-style rapid invocation
# ---------------------------------------------------------------------------

class TestQueuePostIdUniqueness:
    def test_queue_post_generates_unique_record_paths_across_many_rapid_invocations(self, tmp_path):
        # Arrange
        from queue_post import queue_post

        content_path = _write_content_file(tmp_path, "content\n")
        invocation_count = 300

        # Act
        record_paths = [
            queue_post(
                target="ADR-400",
                channel="jira-comment",
                content_file=str(content_path),
                event_context="after-implement",
            )
            for _ in range(invocation_count)
        ]

        # Assert
        assert len(set(record_paths)) == invocation_count


# ---------------------------------------------------------------------------
# queue_post — DEV_TEAM_STATE_DIR override
# ---------------------------------------------------------------------------

class TestQueuePostStateDirOverride:
    def test_queue_post_writes_under_dev_team_state_dir_override_not_real_home(self, tmp_path):
        # Arrange
        from queue_post import queue_post

        content_path = _write_content_file(tmp_path, "content\n")

        # Act
        record_path = queue_post(
            target="ADR-400",
            channel="jira-comment",
            content_file=str(content_path),
            event_context="after-implement",
        )

        # Assert
        assert str(record_path).startswith(str(tmp_path))
        assert not str(record_path).startswith(str(Path.home() / ".dev-team"))


# ---------------------------------------------------------------------------
# main() CLI wrapper
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_prints_record_path_and_writes_file_on_success(
        self, tmp_path, monkeypatch, capsys
    ):
        # Arrange
        import queue_post

        content_path = _write_content_file(tmp_path, "content\n")
        monkeypatch.setattr(
            sys, "argv",
            [
                "queue_post.py",
                "--target", "ADR-400",
                "--channel", "jira-comment",
                "--content-file", str(content_path),
                "--event-context", "after-implement",
            ],
        )

        # Act
        queue_post.main()

        # Assert
        printed_path = Path(capsys.readouterr().out.strip())
        assert printed_path.is_file()

    def test_main_prints_error_and_exits_nonzero_for_invalid_channel(
        self, tmp_path, monkeypatch, capsys
    ):
        # Arrange
        import queue_post

        content_path = _write_content_file(tmp_path, "content\n")
        monkeypatch.setattr(
            sys, "argv",
            [
                "queue_post.py",
                "--target", "ADR-400",
                "--channel", "slack-message",
                "--content-file", str(content_path),
                "--event-context", "after-implement",
            ],
        )

        # Act / Assert
        with pytest.raises(SystemExit) as exc_info:
            queue_post.main()
        assert exc_info.value.code != 0
        assert capsys.readouterr().err.startswith("Error: ")

    def test_main_prints_error_and_exits_nonzero_for_missing_content_file(
        self, tmp_path, monkeypatch, capsys
    ):
        # Arrange
        import queue_post

        missing_path = tmp_path / "does-not-exist.txt"
        monkeypatch.setattr(
            sys, "argv",
            [
                "queue_post.py",
                "--target", "ADR-400",
                "--channel", "jira-comment",
                "--content-file", str(missing_path),
                "--event-context", "after-implement",
            ],
        )

        # Act / Assert
        with pytest.raises(SystemExit) as exc_info:
            queue_post.main()
        assert exc_info.value.code != 0
        assert capsys.readouterr().err.startswith("Error: ")
