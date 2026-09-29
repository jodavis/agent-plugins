Summary: Run procedure for the gather-pr-evidence skill's dry-run harness — how to materialize
each scenario and grade the subagent's returned JSON evidence bundle.

# gather-pr-evidence: skill dry-run harness

This directory is the fixture set and run procedure for verifying `gather-pr-evidence`
(`plugins/dev-team/skills/gather-pr-evidence/SKILL.md`), a Testable agent-skill-prose component
per `component-taxonomy` — its own action is "return a structured JSON value from a subagent
turn," not a git-state mutation, so it doesn't fit AAA unit tests. Per the taxonomy, it's verified
by "whatever mechanism actually fits": here, a scripted fixture-scenario harness that builds a
local worktree with a real work-tracking configuration, points the skill at a real, already-merged
PR, runs the skill in a fresh subagent, and grades the returned JSON against each scenario's
expected shape.

## Fixture contents

| Path | Purpose |
|---|---|
| `build_fixture.py` | Builds one of two named scenarios: a throwaway local git repo (standing in for the worktree/clone path) with a `.dev-team/config.yaml` configuring both `jira` and `github` work-tracking providers, plus the identity of a real PR in `jodavis/agent-plugins` to fetch evidence for |
| `test_build_fixture.py` | Unit tests confirming each scenario actually produces the worktree/config state and PR identity it claims to, so a dry run always starts from a trustworthy, reproducible state |

Neither `build_fixture.py` nor `test_build_fixture.py` makes a network call — the PR each scenario
points at is only fetched live during Step 2 below.

## Scenarios

| Name | PR | Branch / body | Expected `related_work_items` |
|---|---|---|---|
| `with-related-items` | `jodavis/agent-plugins#103` | branch `dev/claude/Issue-93`; body mentions both `Issue-93` and `ADR-314` | one entry each for `provider: "jira"` (id matching `ADR-314`) and `provider: "github"` (id matching `Issue-93`) |
| `no-related-items` | `jodavis/agent-plugins#230` | branch `dev/claude/plugin-version-check`; body contains neither pattern | `[]` |

Both scenarios configure identical `work-tracking` patterns (`jira`: `ADR-\d+`, `github`:
`Issue-\d+` — this repo's own real config, reused rather than invented); only the chosen PR's
actual content differs between them.

## Invocation model: on-demand, not CI

Like `fixtures/run-hook-instructions`, this harness is **run by the implementing or validating
agent whenever `gather-pr-evidence` is edited** — it is not a CI gate. Grading the returned JSON
against a live PR's actual current content isn't deterministic enough for a reliable automated
gate; `test_build_fixture.py` is the part of this harness that *is* CI-appropriate, and runs in
the normal pytest suite alongside everything else in this repo.

## Step 1 — Materialize a scenario

```bash
python3 plugins/dev-team/fixtures/gather-pr-evidence/build_fixture.py \
  with-related-items /tmp/dry-run/gather-pr-evidence/with-related-items
```

Replace `with-related-items` with `no-related-items` for the other scenario. Each invocation is
idempotent given a fresh destination directory — always materialize into a location outside
version control (e.g. under `/tmp/dry-run/`), and use a fresh destination directory per run rather
than reusing one from a previous dry run.

The command prints the fixture worktree's path, the `owner/repo#number` PR reference to pass the
skill, and the expected `related_work_items` outcome.

## Step 2 — Run the target skill in a fresh subagent

Spawn a fresh `general-purpose` subagent — never a `fork` — with no memory of this harness's
authoring context, so the run exercises `gather-pr-evidence`'s own prose exactly as a first-time
reader would:

```
Agent(subagent_type: "general-purpose", description: "Dry run gather-pr-evidence",
      prompt: "Follow plugins/dev-team/skills/gather-pr-evidence/SKILL.md's instructions in full.
Arguments: <worktree path from Step 1> <pr_ref from Step 1>")
```

Record the subagent's final message verbatim — it must be exactly one JSON object with no
surrounding prose (this is itself part of what Step 3 grades).

## Step 3 — Grade the result

### Mechanical checks

Parse the recorded final message as JSON and check:

- All four top-level keys (`diff`, `description`, `comments`, `related_work_items`) are present.
- `diff` and `description` are non-empty strings (both PRs used by these scenarios have a real
  diff and a non-empty body).
- `comments` is a list (may be empty — neither fixture PR is guaranteed to have inline review
  comments at grading time; this key's mere presence as a list is what's checked, not its length).
- `with-related-items`: `related_work_items` has exactly one entry with `provider: "jira"` and one
  entry with `provider: "github"`; neither entry's `id` or `summary` is empty.
- `no-related-items`: `related_work_items` is exactly `[]`.

### Judgment-shaped checks

- The subagent's final message contains nothing but the JSON object — no preceding explanation,
  no trailing commentary (confirms the skill's "no prose before or after it" instruction was
  followed, and that intermediate tool-call reasoning didn't leak into the return value).
- For `with-related-items`, the resolved `summary` field for each entry plausibly matches the real
  issue/PR title for that id (not a placeholder or hallucinated value).
- For `no-related-items`, confirm (by reading the subagent's own transcript, not just its final
  message) that it reached this result by actually scanning the description/branch name and
  finding no match — not by skipping the scan step entirely.

## Re-running after a skill edit

1. Re-materialize each scenario (Step 1) into a fresh destination — never reuse a previous dry
   run's worktree.
2. Re-run Steps 2–3 against the edited skill for both scenarios.
3. If a checklist item now fails, the edit introduced a regression — fix it before merging, the
   same way a failing unit test blocks a merge elsewhere in this repo.

No fixture content changes as part of a routine re-run. Fixtures only change if
`gather-pr-evidence`'s own contract changes (e.g. its argument shape or the evidence bundle's
shape), in which case update `build_fixture.py` and `test_build_fixture.py` together, and note it
in that change's PR. If the real PRs referenced above are ever deleted or their content changes
in a way that breaks a scenario's expectation, replace them with a different real,
already-merged PR in the same repo that satisfies the scenario's pattern-match requirement.
