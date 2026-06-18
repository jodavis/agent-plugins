#!/usr/bin/env bash
# wait-pr-checks.sh — Block until PR checks complete, then output pass/fail result.
#
# Usage: wait-pr-checks.sh <pr-url>
#
# Polls `gh pr checks` in a loop until no checks remain in the "pending" bucket,
# then inspects the final states. Outputs one of:
#   passed - all checks passed
#   failed - one or more checks failed or were cancelled
#   failed - checks still pending after timeout
#
# Exit code is 0 when all checks pass, 1 when checks fail or time out.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $(basename "$0") <pr-url>" >&2
    exit 1
fi

pr_url="$1"

TIMEOUT_SECONDS=1800  # 30 minutes
POLL_INTERVAL=15
elapsed=0

# Poll until no checks are pending (or timeout).
while [[ $elapsed -lt $TIMEOUT_SECONDS ]]; do
    pending=$(gh pr checks "$pr_url" --json bucket \
        --jq '[.[] | select(.bucket == "pending")] | length' 2>/dev/null || echo "0")

    if [[ "$pending" -eq 0 ]]; then
        break
    fi

    echo "Waiting for $pending check(s) to complete... (${elapsed}s elapsed)" >&2
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))
done

if [[ $elapsed -ge $TIMEOUT_SECONDS ]]; then
    echo "failed - checks still pending after ${TIMEOUT_SECONDS}s timeout"
    exit 1
fi

# All checks have settled — inspect final states.
failing=$(gh pr checks "$pr_url" --json bucket \
    --jq '[.[] | select(.bucket == "fail" or .bucket == "cancel")] | length' \
    2>/dev/null || echo "0")

if [[ "$failing" -gt 0 ]]; then
    echo "failed - $failing check(s) failed or were cancelled"
    exit 1
fi

echo "passed - all checks passed"
