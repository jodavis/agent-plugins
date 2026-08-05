Summary: Run procedure for the run-hook-instructions skill's dry-run harness — how to materialize
each instructions-map scenario and grade the skill's output against expected git/return-value
state.

# run-hook-instructions: skill dry-run harness

This directory is the fixture set and run procedure for verifying `run-hook-instructions`
(`plugins/dev-team/skills/run-hook-instructions/SKILL.md`), a Testable agent-skill-prose component
per `component-taxonomy` — it makes judgment calls about which real operation fits a freeform
instruction string, so it doesn't fit AAA unit tests. Per the taxonomy, it's verified by
"whatever mechanism actually fits": here, a scripted fixture-scenario harness that builds a real
git repo and an already-resolved `instructions` map, runs the skill against it, and asserts the
resulting git state and the skill's own reported outcome.

`dev_team.py` owns resolving which config keys apply and in what order (see
`get-project-configuration/SKILL.md`'s `instructions` section) — this skill only dispatches an
already-resolved map, so this harness hands one over directly rather than building a
`Project Configuration` section for the skill to parse itself.

## Fixture contents

| Path | Purpose |
|---|---|
| `build_fixture.py` | Builds one of three named scenarios: a throwaway git repo with an uncommitted change, a throwaway context file, and an already-resolved `instructions` map to pass via `--instructions` |
| `test_build_fixture.py` | Unit tests confirming each scenario actually produces the repo/instructions-map state it claims to, so a dry run always starts from a trustworthy, reproducible state |

Every scenario uses a local commit (not a push) as its observable action, so no fixture remote is
needed.

## Scenarios

| Name | `--instructions` map | Expected `run-hook-instructions` return | Expected new local commit? |
|---|---|---|---|
| `commit-entry` | `commit-uncommitted: "Commit any uncommitted changes"` | `successful` | Yes |
| `disabled-entry` | `commit-uncommitted: ""` | `successful` | No |
| `unrecognized-instruction` | `recite-hamlet: "Recite three lines from Hamlet"` | anything other than `successful` | No |

`disabled-entry` proves the skip-empty-value behavior is externally observable, not just
internal logic: the same label used in `commit-entry`, overridden to `""`, must produce no
commit. `unrecognized-instruction` proves the skill doesn't silently no-op an instruction it
doesn't recognize — it must attempt something and report failure, not a false success.

## Invocation model: on-demand, not CI

Like `fixtures/resolve-rebase-conflict`, this harness is **run by the implementing or validating
agent whenever `run-hook-instructions` is edited** — it is not a CI gate. The judgment-shaped
grading (did the skill correctly decline to fabricate success for an unrecognized instruction?)
isn't deterministic enough for a reliable automated gate; `test_build_fixture.py` is the part of
this harness that *is* CI-appropriate, and should run in the normal pytest suite alongside
everything else in this repo.

## Step 1 — Materialize a scenario

```bash
python3 plugins/dev-team/fixtures/run-hook-instructions/build_fixture.py \
  commit-entry /tmp/dry-run/run-hook-instructions/commit-entry
```

Replace `commit-entry` with `disabled-entry` or `unrecognized-instruction` for the other two
scenarios. Each invocation is idempotent given a fresh destination directory — always
materialize into a location outside version control (e.g. under `/tmp/dry-run/`), and use a
fresh destination directory per run rather than reusing one from a previous dry run.

The command prints the fixture git repo's path, the throwaway context file's path, the
`--instructions` JSON to pass the skill, and the expected return value and commit outcome.

## Step 2 — Run the target skill in a clean session

Start a fresh session with no memory of this harness's authoring context — a validating
subagent blind to why the fixtures look the way they do, so the run exercises the skill's prose
exactly as a first-time reader would. Give it only:

- `run-hook-instructions`'s own `SKILL.md` instructions,
- the materialized worktree path from Step 1, checked out as the session's working directory,
- the `--instructions <instructions JSON from Step 1> --context-file <context_file path from
  Step 1>` arguments.

Run the skill to completion and record its returned text.

## Step 3 — Grade the result

### Mechanical checks

Run these against the same worktree path from Step 1, after Step 2 completes:

```bash
# Commit count: 1 (unchanged) or 2 (one new commit), depending on scenario.
git -C <worktree> rev-list --count HEAD

# Working tree state.
git -C <worktree> status --porcelain
```

- **`commit-entry`:** the skill must return exactly `successful`; commit count must be `2` (one
  new commit beyond the fixture's initial commit); `git status --porcelain` must be empty (the
  uncommitted change was committed).
- **`disabled-entry`:** the skill must return exactly `successful`; commit count must stay `1`;
  `git status --porcelain` must still show the original uncommitted change, untouched.
- **`unrecognized-instruction`:** the skill's return must NOT be `successful`; commit count must
  stay `1`; `git status --porcelain` must still show the original uncommitted change, untouched
  (the instruction has nothing to do with committing, so nothing should change here either way —
  this is a sanity check that the skill didn't do something unrelated and call it success).

### Judgment-shaped checks

Read the skill's own report against each scenario's expectation:

- **`commit-entry`:** the skill's report describes actually creating a commit for the
  uncommitted change (via `commit-changes` or equivalent), not just asserting success.
- **`disabled-entry`:** the skill's report explains that the `commit-uncommitted` entry was
  skipped because its value is empty — not that it attempted and somehow produced no commit.
- **`unrecognized-instruction`:** the skill's report explains that it attempted to find an
  operation fitting "Recite three lines from Hamlet" and found none, rather than silently
  treating the entry as done. A skill that returns `successful` here fails this scenario
  regardless of what (if anything) it actually did — the check is "did it avoid a false
  success," not "did it produce a clever attempt."

## Re-running after a skill edit

1. Re-materialize each scenario (Step 1) into a fresh destination — never reuse a previous dry
   run's worktree.
2. Re-run Steps 2–3 against the edited skill for all three scenarios.
3. If a checklist item now fails, the edit introduced a regression — fix it before merging, the
   same way a failing unit test blocks a merge elsewhere in this repo.

No fixture content changes as part of a routine re-run. Fixtures only change if
`run-hook-instructions`'s own contract changes (e.g. its argument shape), in which case update
`build_fixture.py` and `test_build_fixture.py` together and note it in that change's PR.
