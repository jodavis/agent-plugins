#!/usr/bin/env python3
"""Run this project's validation commands, as configured in project configuration.

Usage: run_validation.py --repo-root <path>

Reads the merged project configuration's `validation` key as a list of shell command
strings (see get-project-configuration's `validation` section) and runs each one in
order from the repo root, stopping at the first failing command — fail-fast, matching
the `set -euo pipefail` semantics of the `scripts/validate.sh` convention this replaces.

A project with no `validation` configured (null, absent, or an empty list) exits 0
immediately without running anything — the same "no validation configured" opt-out
`get-project-configuration` already documents for `work-tracking: null`.

Prints each command before running it, and the failing command's exit code to stderr on
failure. Deliberately does not print a JSON status line: workflow-script derives its
literal "Succeeded"/"Failed: ..." result from this script's plain exit code, the same way
it already does for scripts/validate.sh.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "get-project-configuration" / "scripts"))
from merge_config import YamlParseError, build_merged_config  # noqa: E402

COMMAND_TIMEOUT_SECONDS = 1800  # 30 minutes; validation may run a full build + test suite


def run_commands(commands: list[str] | None, repo_root: Path, run=subprocess.run) -> int:
    """Run each command string in `commands` in order from `repo_root`, stopping at the
    first failure. Returns 0 if every command succeeds (or `commands` is empty/None), or
    the failing command's exit code."""
    if not commands:
        return 0
    for command in commands:
        print(f"+ {command}")
        result = run(command, shell=True, cwd=repo_root, timeout=COMMAND_TIMEOUT_SECONDS)
        if result.returncode != 0:
            print(f"Command failed with exit code {result.returncode}: {command}", file=sys.stderr)
            return result.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    try:
        config = build_merged_config(repo_root)
    except (YamlParseError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return run_commands(config.get("validation"), repo_root)


if __name__ == "__main__":
    sys.exit(main())
