#!/usr/bin/env python3
"""Queue one pending-post record instead of posting content immediately.

`queue_post.py --target <key-or-pr-url> --channel <channel> --content-file <path>
--event-context <event>` writes a YAML record (`target`, `channel`, `content`, `event_context`,
`created_at`) to `<state-dir>/<repo-slug>/pending-posts/<id>.yaml`. `content` is always read from
`--content-file` — never passed inline or via stdin — so arbitrary, possibly multi-line comment
text never appears in a shell command string. This is the foundational piece that lets later
pipeline steps queue status-comment content for human review instead of posting it immediately
(see the ADR-398 spec's later tasks: `run-hook-instructions`, `investigate-bug`,
`user-approve-posts`).

Deterministic and side-effect-free beyond writing the one record file: no locking, no
agent/MCP calls, no judgment about what to do with the record afterward. Uniqueness across
concurrent callers is structural — each `<id>` is a timestamp prefix plus a random suffix —
rather than lock-based.

Usage: queue_post.py --target <key-or-pr-url> --channel <channel> --content-file <path>
                      --event-context <event>

Prints the written record's path to stdout on success (exit 0).
Prints "Error: ..." to stderr and exits 1 on any failure (missing/unreadable content file,
invalid channel).
"""

import argparse
import datetime
import os
import secrets
import sys
from pathlib import Path

_WORKFLOW_ORCHESTRATE_SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent / "workflow-orchestrate" / "scripts"
)
sys.path.insert(0, str(_WORKFLOW_ORCHESTRATE_SCRIPTS))
from get_context_path import get_repo_slug  # noqa: E402

CHANNELS = ("jira-comment", "jira-description", "github-issue-comment", "pr-comment")


def _state_dir() -> Path:
    """Root of the dev-team state tree: `DEV_TEAM_STATE_DIR` if set (a test seam — never set in
    production), otherwise `~/.dev-team`."""
    base_env = os.environ.get("DEV_TEAM_STATE_DIR")
    return Path(base_env) if base_env else Path.home() / ".dev-team"


def _pending_posts_dir(repo_slug: str) -> Path:
    return _state_dir() / repo_slug / "pending-posts"


def _generate_id() -> str:
    """A timestamp-prefixed random suffix. Collision-free under concurrent callers without any
    locking: even two calls landing in the same second get independent random suffixes."""
    timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    suffix = secrets.token_hex(4)
    return f"{timestamp}-{suffix}"


def _quote_scalar(value: str) -> str:
    """Double-quote a plain scalar field, escaping backslashes and double quotes, so it
    round-trips through `merge_config.parse_yaml`'s double-quoted scalar path regardless of what
    characters `value` contains (colons, quotes, leading/trailing whitespace, etc.)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_content_block(content: str) -> str:
    """Render `content` as a literal (`|`) block scalar under a `content:` key, matching the
    shape `merge_config.py`'s `_parse_block_scalar_literal` reads back: a `content: |` header
    followed by every line indented two spaces past the key. Blank lines are written empty (no
    trailing whitespace) since the reader doesn't require indentation on them, and clip chomping
    (the default for a bare `|`) always restores exactly one trailing newline on read, so a
    trailing `\\n` split into an empty final element is dropped here rather than written twice."""
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    body = "\n".join(f"  {line}" if line else "" for line in lines)
    return f"content: |\n{body}" if body else "content: |"


def build_record_yaml(
    target: str, channel: str, content: str, event_context: str, created_at: str
) -> str:
    """Hand-written YAML matching `merge_config.parse_yaml`'s supported subset: quoted plain
    scalars for `target`/`channel`/`event_context`/`created_at`, and a literal block scalar for
    `content` (the only field expected to contain newlines or other arbitrary text)."""
    lines = [
        f"target: {_quote_scalar(target)}",
        f"channel: {_quote_scalar(channel)}",
        _format_content_block(content),
        f"event_context: {_quote_scalar(event_context)}",
        f"created_at: {_quote_scalar(created_at)}",
    ]
    return "\n".join(lines) + "\n"


def queue_post(target: str, channel: str, content_file: str, event_context: str) -> Path:
    """Write one pending-post record and return its path. Raises `ValueError` for an invalid
    `channel` or an unreadable `content_file` — never lets a lower-level exception like
    `OSError` propagate — so `main()` can report both failure modes the same way."""
    if channel not in CHANNELS:
        raise ValueError(f"invalid channel {channel!r}; must be one of {', '.join(CHANNELS)}")

    try:
        content = Path(content_file).read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"could not read content file {content_file!r}: {e}") from e

    repo_slug = get_repo_slug()
    posts_dir = _pending_posts_dir(repo_slug)
    posts_dir.mkdir(parents=True, exist_ok=True)

    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record_yaml = build_record_yaml(target, channel, content, event_context, created_at)

    record_path = posts_dir / f"{_generate_id()}.yaml"
    record_path.write_text(record_yaml, encoding="utf-8")
    return record_path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="queue_post.py",
        description="Queue one pending-post YAML record instead of posting content immediately.",
    )
    parser.add_argument("--target", required=True, help="Jira/GitHub issue key or PR URL")
    parser.add_argument("--channel", required=True, help=f"One of: {', '.join(CHANNELS)}")
    parser.add_argument(
        "--content-file", required=True, help="Path to a file containing the post content"
    )
    parser.add_argument(
        "--event-context", required=True, help="Pipeline event this post was queued from"
    )
    args = parser.parse_args()

    try:
        record_path = queue_post(args.target, args.channel, args.content_file, args.event_context)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(record_path, flush=True)


if __name__ == "__main__":
    main()
