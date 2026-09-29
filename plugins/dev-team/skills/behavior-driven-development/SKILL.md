---
name: behavior-driven-development
user-invocable: false
---

## Steps

### 1 — Write E2E / API tests first

Write Gherkin scenarios that cover the exit criteria before writing any implementation code. Use existing steps whenever possible. When new steps are needed:
- Use generalized `When` / `Then` / `Given` phrasing — each step should be something a human could do or observe manually
- Step definitions delegate logic to test service methods

Run the new scenarios and confirm they fail. A failure here means "not implemented yet" — if they fail for a build or infrastructure reason instead, fix that first.

### 2 — Confirm E2E tests pass

Once implementation is complete, run the full E2E scenario suite and confirm all new scenarios pass.
