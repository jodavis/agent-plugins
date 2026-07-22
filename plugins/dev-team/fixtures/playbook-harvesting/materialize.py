#!/usr/bin/env python3
"""Materialize a fixture exemplar's scripted git history into a throwaway git repository.

Usage: materialize.py <exemplar-dir> <output-dir>

`<exemplar-dir>` must contain a `commits.json` manifest — a JSON list of
`{"dir": "<snapshot-dir-name>", "message": "<commit message>"}` entries, in commit order —
plus one snapshot directory per manifest entry holding a full copy of the working tree at
that commit.

`<output-dir>` is removed and rebuilt from scratch on every run, so materializing is
idempotent: re-running against the same exemplar always reproduces the same commit history.
No `.git` directory is ever checked into this repo — `<output-dir>` is meant to be a scratch
location outside version control.

Prints "Error: ..." to stderr and exits 1 on any failure. Exits 0 on success.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path


class MaterializeError(Exception):
    """Raised for any expected failure while materializing an exemplar."""


def load_manifest(exemplar_dir: Path) -> list[dict]:
    """Read and validate `<exemplar_dir>/commits.json`.

    Raises MaterializeError if the manifest is missing, malformed, or empty.
    """
    manifest_path = exemplar_dir / "commits.json"
    if not manifest_path.is_file():
        raise MaterializeError(f"no commits.json manifest found at {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MaterializeError(f"{manifest_path} is not valid JSON: {e}") from e

    if not isinstance(manifest, list):
        raise MaterializeError(f"{manifest_path} must be a JSON list of commit entries")
    if not manifest:
        raise MaterializeError(f"{manifest_path} is empty; at least one commit entry is required")

    for entry in manifest:
        _validate_entry_shape(manifest_path, entry)

    return manifest


def _validate_entry_shape(manifest_path: Path, entry: object) -> None:
    """Raise MaterializeError unless `entry` is a dict with string `dir` and `message` keys."""
    if not isinstance(entry, dict):
        raise MaterializeError(
            f"{manifest_path} entry {entry!r} must be a JSON object with 'dir' and 'message' keys"
        )
    for key in ("dir", "message"):
        if key not in entry:
            raise MaterializeError(f"{manifest_path} entry {entry!r} is missing required key {key!r}")
        if not isinstance(entry[key], str):
            raise MaterializeError(
                f"{manifest_path} entry {entry!r} has non-string value for key {key!r}"
            )


def validate_snapshots_exist(exemplar_dir: Path, manifest: list[dict]) -> None:
    """Raise MaterializeError if any manifest entry's snapshot directory is missing."""
    for entry in manifest:
        snapshot_dir = exemplar_dir / entry["dir"]
        if not snapshot_dir.is_dir():
            raise MaterializeError(
                f"manifest entry {entry['dir']!r} has no matching snapshot directory "
                f"at {snapshot_dir}"
            )


def _run_git(output_dir: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(output_dir), *args],
        check=True, capture_output=True, text=True, timeout=30,
    )


def _replace_working_tree(output_dir: Path, snapshot_dir: Path) -> None:
    """Clear everything in `output_dir` except `.git`, then copy `snapshot_dir`'s contents in."""
    for entry in output_dir.iterdir():
        if entry.name == ".git":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    shutil.copytree(snapshot_dir, output_dir, dirs_exist_ok=True)


def materialize(exemplar_dir: Path, output_dir: Path) -> None:
    """Replay `exemplar_dir`'s scripted commit history into a fresh git repo at `output_dir`."""
    manifest = load_manifest(exemplar_dir)
    validate_snapshots_exist(exemplar_dir, manifest)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    _run_git(output_dir, "init", "--quiet")
    _run_git(output_dir, "config", "user.email", "fixture@example.invalid")
    _run_git(output_dir, "config", "user.name", "Fixture Materializer")

    for entry in manifest:
        _replace_working_tree(output_dir, exemplar_dir / entry["dir"])
        _run_git(output_dir, "add", "-A")
        _run_git(output_dir, "commit", "--quiet", "-m", entry["message"])


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: materialize.py <exemplar-dir> <output-dir>", file=sys.stderr)
        sys.exit(1)

    exemplar_dir = Path(sys.argv[1]).expanduser()
    output_dir = Path(sys.argv[2]).expanduser()

    try:
        materialize(exemplar_dir, output_dir)
    except MaterializeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: git command failed: {e.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"Materialized {output_dir}")


if __name__ == "__main__":
    main()
