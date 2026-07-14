---
name: implement-task
user-invocable: false
description: >
  Use when implementing a task from a task brief.
  Reads the task brief, loads developer standards, then dispatches each in-scope component to
  implement-direct or implement-tdd, triages any leftover exit-criteria work into an ad hoc
  component or non-component-shaped work, re-runs E2E scenarios, self-reviews, and returns a
  work summary.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- You need to implement a task from a task brief
- You are writing new code for a work item

You are reading the workflow context file to find a task brief, dispatching each in-scope
component to the skill that matches its testing tier, triaging any exit-criteria work that
isn't captured by a declared component, and committing changes locally to the repo.

## Steps

### 1 — Get information about the current task

Use the `use-context-file` skill with the argument this skill received (a `work-item-id` or a
context-file path) to resolve, initialize, and read the context file. This determines
`work-item-id` directly.

### 2 — Get the task brief

Use the `read-task-brief` skill with the `work-item-id` to load the task brief and ensure the working branch is set up.

### 3 — Load developer standards

Use the `developer-standards` skill to load code guidelines and quality gates.

**IMPORTANT**: In this workflow, full validation is the responsibility of another agent. Build and test only the code you modified — do not run the full validation suite.

### 4 — Understand the task

Read the task brief in full. Identify:

- The exit criteria — these define what "done" means
- Files to create or modify, and the design decisions that constrain each
- Existing utilities, base classes, and patterns to reuse (the brief will call these out)
- Whether the brief has a **Components in scope** section, and if so, the components it lists
  and their dependency order (see step 6)

If anything in the brief is ambiguous and the ambiguity would affect correctness, note it in your work summary and resolve it conservatively.

### 5 — Write E2E scenarios first

Use the `behavior-driven-development` skill's step 1, by name: write Gherkin scenarios covering
the exit criteria before any implementation exists, run them, and confirm they fail for the
right reason.

### 6 — Dispatch declared components

If the task brief's **Components in scope** section lists one or more components, dispatch each
one to its own implementation skill, in the dependency order the list already reflects:

- Tier `Wrapper` or `Orchestrator` → invoke the `implement-direct` skill with the component row,
  the task brief path, and the spec path.
- Tier `Testable` → invoke the `implement-tdd` skill with the same three arguments.

Each of these skills implements its own component and performs its own `commit-changes` call
before returning — one commit per component. Do not commit again in this skill for any
component handled this way.

If the Components in scope section is absent entirely, or present but explicitly empty
(`write-task-brief`'s `(none — this task touches no classified components)` convention), there
is nothing to dispatch here — go straight to step 7.

### 7 — Triage leftover work

After every declared component (if any) is dispatched, check the exit criteria against what's
actually been built so far. Run this step every time — never skip it just because a components
list existed and was fully dispatched; confirm there's genuinely nothing left instead of
assuming it. Anything not yet covered — including the entire task, when there was no Components
in scope section at all — falls into one of two buckets:

- **Component-shaped but uncaptured** — work that would have earned its own Wrapper/Testable/
  Orchestrator row had it been called out in the brief's Components in scope list, but wasn't
  (this is also the whole task, when the brief had no Components in scope section at all — that
  case collapses into this bucket rather than a separate procedure). Use the `component-taxonomy`
  skill to classify it on the spot, then route it through `implement-direct` or `implement-tdd`
  exactly like a declared component — the same per-component `commit-changes` call from that
  skill, not a commit made here.
- **Not component-shaped at all** — glue/wiring, one-off scripts, file moves or renames,
  documentation, dry runs, or anything else that doesn't fit the Wrapper/Testable/Orchestrator
  taxonomy (illustrative, not exhaustive — recognize non-component-shaped work rather than
  matching it against a checklist). Implement this directly: no `component-taxonomy` call, no
  TDD loop, no dedicated commit. Stage it (`git add -A`, or the target project's VCS equivalent)
  and leave it for the final commit in step 10.

### 8 — Confirm E2E scenarios pass

Use the `behavior-driven-development` skill's step 2, by name: run the full new-scenario suite
and confirm all new scenarios pass.

### 9 — Self-review

Review the diff as if you were doing a code review. This covers the cumulative diff across every
per-component commit made for this task in steps 6–7, plus whatever non-component-shaped work is
staged but not yet committed from step 7 — not just one flow's output:

- Does every exit criterion have demonstrable coverage (code + test)?
- Are there missing test cases (branches, error paths, invalid inputs)?
- Do all files follow the standards loaded in step 3?
- Is there any scope creep — changes not required by the brief?
- For each dispatched or ad hoc component, was its tier-appropriate test expectation honored — no
  dedicated test for a `Wrapper` (expected, not a gap), a narrow primary-scenario integration
  test for an `Orchestrator`, and full branch/error/boundary/logging coverage for a `Testable`
  component? Treat a `Wrapper`'s absent test, and an `Orchestrator`'s narrower-than-Testable
  coverage, as expected per `implement-direct`'s own self-review notes — not gaps to flag.

Fix anything this review surfaces before continuing to step 10 — a review finding must not be
left for the final commit to paper over silently.

### 10 — Final commit

Use the `commit-changes` skill to make one final commit covering: any non-component-shaped work
staged in step 7, plus any fix step 9's self-review required. Skip this step only when there is
genuinely nothing left to commit — every exit criterion was already satisfied by classified or ad
hoc components, and step 9 found nothing to fix. Never skip it just because a Components in scope
list was non-empty — the per-component commits from steps 6–7 are unaffected either way.

### 11 — Report

Return a work summary as structured prose:

**Files created or modified**
List each file by path with a one-line description of what changed.

**Key decisions made**
Anything not dictated by the brief that you chose during implementation (design choices, interface splits, tradeoffs). Omit this section if there are none.

**Unit tests**
File path(s) and test method names for all new or modified unit tests.

**E2E scenarios**
Feature file path(s) and scenario title(s) for all new or modified Gherkin scenarios.

**Known ambiguities**
Any Tier 3 "best-effort, documented, non-blocking" ambiguity notes bubbled up from an
`implement-tdd` escalation (or recorded directly during this skill's own step 7 triage), for
human review after the fact. Omit this section if there are none.

## Skills

- `behavior-driven-development` — the E2E-first wrapper (step 5) and E2E-confirm wrapper
  (step 8)
- `component-taxonomy` — ad hoc classification of component-shaped but uncaptured work in
  step 7
- `implement-direct` — dispatch target for `Wrapper`/`Orchestrator` components, declared
  (step 6) or ad hoc (step 7)
- `implement-tdd` — dispatch target for `Testable` components, declared (step 6) or ad hoc
  (step 7)
- `commit-changes` — the one final commit in step 10, covering non-component-shaped work plus
  review fixups
