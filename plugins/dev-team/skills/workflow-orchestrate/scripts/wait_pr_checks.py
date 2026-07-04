#!/usr/bin/env python3
"""Block until PR checks complete, then output pass/fail result.

Usage: wait_pr_checks.py <pr-url>

Polls `gh pr checks` in a loop until no checks remain in the "pending" bucket,
then inspects the final states.

Outputs a human-readable summary line followed by a JSON status object:
    {"status": "passed"}
    {"status": "failed", "reason": "<detail>"}

The JSON object is always the last stdout line so workflow-script can write it
directly to the context file section.

Exit code is 0 when all checks pass, 1 when checks fail or time out.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

TIMEOUT_SECONDS = 1800  # 30 minutes
POLL_INTERVAL = 15


def _fail(reason: str) -> None:
    print(f"failed - {reason}")
    print(json.dumps({"status": "failed", "reason": reason}))
    sys.exit(1)


def _get_checks(pr_url: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "pr", "checks", pr_url, "--json", "bucket"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        _fail(f"failed to query PR checks: {detail}")
    return json.loads(result.stdout)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {Path(sys.argv[0]).name} <pr-url>", file=sys.stderr)
        sys.exit(1)

    pr_url = sys.argv[1]

    elapsed = 0
    while elapsed < TIMEOUT_SECONDS:
        checks = _get_checks(pr_url)
        pending = sum(1 for c in checks if c.get("bucket") == "pending")
        if pending == 0:
            break
        print(f"Waiting for {pending} check(s) to complete... ({elapsed}s elapsed)", file=sys.stderr)
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    else:
        _fail(f"checks still pending after {TIMEOUT_SECONDS}s timeout")

    checks = _get_checks(pr_url)
    failing = sum(1 for c in checks if c.get("bucket") in ("fail", "cancel"))
    if failing > 0:
        _fail(f"{failing} check(s) failed or were cancelled")

    print("passed - all checks passed")
    print(json.dumps({"status": "passed"}))


if __name__ == "__main__":
    main()
