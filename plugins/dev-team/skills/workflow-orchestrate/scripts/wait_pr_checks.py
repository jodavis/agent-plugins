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

# A branch/PR with genuinely zero registered checks makes `gh pr checks` exit non-zero with a
# message to that effect — indistinguishable by exit code alone from a real query failure (bad
# auth, network error, ...). Retried a few times first (#206): CI can take a few seconds to
# register its first check after a push, and treating that transient race as "no CI configured"
# on the very first look would wrongly bless a branch whose checks just hadn't started reporting
# yet.
ZERO_CHECKS_MAX_ATTEMPTS = 3
ZERO_CHECKS_RETRY_INTERVAL = 20


def _fail(reason: str) -> None:
    print(f"failed - {reason}")
    print(json.dumps({"status": "failed", "reason": reason}))
    sys.exit(1)


def _is_no_checks_error(detail: str) -> bool:
    """Matches `gh pr checks`' own wording for a branch/PR with no registered checks at all —
    case-insensitively, since exact wording isn't guaranteed stable across gh CLI versions."""
    lowered = detail.lower()
    return "no checks" in lowered or "no status checks" in lowered


def _get_checks(pr_url: str) -> list[dict] | None:
    """Returns the parsed checks list, or None if `gh pr checks` reports zero registered checks
    for this branch/PR — distinct from a real query failure, which calls _fail() and never
    returns."""
    result = subprocess.run(
        ["gh", "pr", "checks", pr_url, "--json", "bucket"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if _is_no_checks_error(detail):
            return None
        _fail(f"failed to query PR checks: {detail}")
    checks = json.loads(result.stdout)
    return checks if checks else None


def _get_checks_with_zero_check_retries(pr_url: str) -> list[dict] | None:
    """Retries a "zero checks reported" result up to ZERO_CHECKS_MAX_ATTEMPTS times before
    concluding the branch genuinely has no CI configured. Returns None only after every retry
    still came back empty."""
    checks = None
    for attempt in range(1, ZERO_CHECKS_MAX_ATTEMPTS + 1):
        checks = _get_checks(pr_url)
        if checks is not None:
            return checks
        if attempt < ZERO_CHECKS_MAX_ATTEMPTS:
            print(
                f"No checks reported yet — retrying in {ZERO_CHECKS_RETRY_INTERVAL}s "
                f"({attempt}/{ZERO_CHECKS_MAX_ATTEMPTS})...",
                file=sys.stderr,
            )
            time.sleep(ZERO_CHECKS_RETRY_INTERVAL)
    return None


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {Path(sys.argv[0]).name} <pr-url>", file=sys.stderr)
        sys.exit(1)

    pr_url = sys.argv[1]

    checks = _get_checks_with_zero_check_retries(pr_url)
    if checks is None:
        # No CI configured for this branch/PR at all — nothing to block signoff on.
        print("passed - no CI checks are configured for this branch")
        print(json.dumps({"status": "passed", "note": "no checks configured"}))
        return

    elapsed = 0
    while elapsed < TIMEOUT_SECONDS:
        pending = sum(1 for c in checks if c.get("bucket") == "pending")
        if pending == 0:
            break
        print(f"Waiting for {pending} check(s) to complete... ({elapsed}s elapsed)", file=sys.stderr)
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        checks = _get_checks(pr_url) or checks
    else:
        _fail(f"checks still pending after {TIMEOUT_SECONDS}s timeout")

    failing = sum(1 for c in checks if c.get("bucket") in ("fail", "cancel"))
    if failing > 0:
        _fail(f"{failing} check(s) failed or were cancelled")

    print("passed - all checks passed")
    print(json.dumps({"status": "passed"}))


if __name__ == "__main__":
    main()
