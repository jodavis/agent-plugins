---
name: final-sign-off
user-invocable: false
description: >
  Use when handing off an approved PR to a human reviewer.
  Reports the hand-off's readiness/status for `HandoffStep`; the actual promote/assign/
  request-review work is performed afterward by this event's configured `after-signoff-success`
  instructions (via `run-event-hooks`), not by this skill.
argument-hint: <pr_url> <work-item-id>
---

Use this skill when:
- A review has been approved and the PR is ready for human review
- You need to hand off from agent review to human review

This skill runs only once `signoff` itself has approved (`reviewing`'s own `approved` trigger
routes to `signoff`, never here directly, so a hand-off is never reached without a full signoff
pass). It does not itself promote the PR, assign the Jira issue, or request a review — that work
is performed by this pipeline event's `after-signoff-success` instructions (run generically by
`run-event-hooks`, dispatched around this skill by `workflow-worker` under the `signoff` event
name). This skill's only job is to report that the hand-off point was reached.

## Steps

### 1 — Report completion

Write a short, non-empty confirmation as this skill's own output — `workflow-worker` places it
into the `Handoff Result` context section, e.g.:

> Hand-off acknowledged for `<pr_url>` (`<work-item-id>`); ready for hand-off instructions.
