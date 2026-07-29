Summary: Run procedure for the workflow-worker / workflow-script `--event` dry-run harness — how
to materialize each target/scenario combination and grade the two skills' before/after
`run-event-hooks` wrapping (added by ADR-361) against expected git/return-value state.

# workflow-worker / workflow-script: `--event` dispatch dry-run harness

This directory is the fixture set and run procedure for verifying the `--event` wrapping ADR-361
added to `plugins/dev-team/skills/workflow-worker/SKILL.md` and
`plugins/dev-team/skills/workflow-script/SKILL.md`. Both are Orchestrator-tier agent-skill prose
per `component-taxonomy` — they call the already-implemented `run-event-hooks` skill (ADR-360)
around one existing invocation and fold its result into their own, which doesn't fit a plain
`pytest` unit test. Per the taxonomy, they are verified by whatever mechanism actually fits: here,
the same scripted fixture-scenario harness model `plugins/dev-team/fixtures/run-event-hooks/`
uses for `run-event-hooks` itself — a throwaway git repo and a throwaway workflow context file
carrying a fictional `instructions` map, dry-run the target skill against it in a clean session,
and grade the resulting git state and the skill's own reported outcome.

## Fixture contents

| Path | Purpose |
|---|---|
| `build_fixture.py` | Builds one of four target/scenario combinations: a throwaway git repo with an uncommitted change, plus a throwaway context file whose `Project Configuration` section carries a fictional `instructions` map, plus the exact CLI argument string to invoke the target skill with |
| `test_build_fixture.py` | Unit tests confirming each combination actually produces the repo/context-file/CLI-argument state it claims to, so a dry run always starts from a trustworthy, reproducible state |

Every combination uses the fictional event `fizzle`, reusing the same fictional-event convention
`run-event-hooks`' own harness established, so this proves the two callers' generic wrapping
mechanics rather than testing today's specific shipped defaults.

## Targets and scenarios

| Target | Skill under test | Wrapped action |
|---|---|---|
| `worker` | `workflow-worker` | `--skill get-project-configuration` (a trivial, side-effect-free existing skill) |
| `script` | `workflow-script` | `--command "python3 -c \"print('Succeeded')\""` (a trivial command whose last line satisfies step 3's `Succeeded`-prefix check) |

| Scenario | `--event` passed? | `before-fizzle` | `after-fizzle` |
|---|---|---|---|
| `with-event` | Yes (`--event fizzle`) | `commit-uncommitted: "Commit any uncommitted changes"` | `recite-hamlet: "Recite three lines from Hamlet"` |
| `no-event` | No | *(same map is present in the context file, but never consulted)* | *(same)* |

`with-event`'s `before-fizzle` entry is commit-producing (proves the before-hook actually ran: the
repo's pre-existing uncommitted change gets committed, before anything else could have). Its
`after-fizzle` entry is deliberately unrecognized (mirrors `run-event-hooks`'s own
`unrecognized-instruction` scenario) so that phase's hook call returns `failed: ...` — proving
both that the after-hook ran and that its failure flips the wrapping skill's own overall result
even though the wrapped skill/command itself succeeded. `no-event` reuses the identical
`instructions` map but never passes `--event` on the CLI — a stronger negative control than
"no instructions configured," proving the omission of `--event` itself (not merely an absent
config) is what suppresses both hook calls.

This directly covers the task brief's three testing-plan scenarios: `worker`/`with-event` is
scenario 1 (the spawn_agent-shaped dry run), `script`/`with-event` is scenario 2 (the run_script
dry run), and `worker`/`no-event` + `script`/`no-event` together are scenario 3 (a plain
no-`--event` invocation of each, confirming byte-for-byte identical behavior to before this
feature existed).

## Invocation model: on-demand, not CI

Like `fixtures/run-event-hooks`, this harness is **run by the implementing or validating agent
whenever `workflow-worker`/`workflow-script`'s `--event` wrapping is edited** — it is not a CI
gate. The judgment-shaped grading (did the before-hook really run first, did the after-hook's
failure really flip the overall result) isn't deterministic enough for a reliable automated gate;
`test_build_fixture.py` is the part of this harness that *is* CI-appropriate, and runs in the
normal pytest suite alongside everything else in this repo.

## Step 1 — Materialize a combination

```bash
python3 plugins/dev-team/fixtures/workflow-event-dispatch/build_fixture.py \
  worker with-event /tmp/dry-run/workflow-event-dispatch/worker-with-event
```

Replace `worker`/`script` and `with-event`/`no-event` for the other three combinations. Each
invocation is idempotent given a fresh destination directory — always materialize into a location
outside version control (e.g. under `/tmp/dry-run/`), and use a fresh destination directory per
run rather than reusing one from a previous dry run.

The command prints the fixture git repo's path, the throwaway context file's path, the exact
`cli_args` string to invoke the target skill with, the expected commit counts before/after the
run, the expected overall-result kind (`successful`/`failed`), and grading notes describing what
to look for.

## Step 2 — Run the target skill in a clean session

Start a fresh session with no memory of this harness's authoring context — a validating subagent
blind to why the fixtures look the way they do, so the run exercises the skill's prose exactly as
a first-time reader would. Give it only:

- the target skill's own `SKILL.md` instructions (`workflow-worker` or `workflow-script`,
  matching the fixture's `target`),
- the materialized worktree path from Step 1, checked out as the session's working directory,
- the `cli_args` string printed by Step 1, verbatim.

Run the skill to completion and record the exact status it reports (`successful` or a detailed
failure description).

## Step 3 — Grade the result

### Mechanical checks

Run these against the same worktree path from Step 1, after Step 2 completes:

```bash
# Commit count: matches expected_commit_count_after_run.
git -C <worktree> rev-list --count HEAD

# Working tree state.
git -C <worktree> status --porcelain
```

- **`with-event` (either target):** commit count must go from 1 to 2 (the before-hook committed
  the pre-existing uncommitted change); `git status --porcelain` must be empty afterward.
- **`no-event` (either target):** commit count must stay at 1; `git status --porcelain` must
  still show the original uncommitted change, untouched (no hook ever ran).
- The context file's write-section (`Dry Run Output` for `worker`, `Dry Run Result` for `script`)
  must contain the wrapped skill/command's actual output in all four combinations — proves the
  wrapped invocation itself always still happens, regardless of `--event`.

### Judgment-shaped checks

Read the skill's own report against each combination's expectation (see each fixture's printed
`grading_notes` for the exact wording):

- **`with-event` (either target):** the skill's report must describe running the before-hook
  first, invoking the wrapped skill/command, then running the after-hook — and must describe the
  overall returned result as a **failure**, explicitly attributing it to the after-hook's
  unrecognized `recite-hamlet`/Hamlet instruction, even though the wrapped skill/command itself
  succeeded. A report that returns `successful` here fails this check regardless of what else it
  got right — the whole point is that a hook failure flips the wrapper's own result.
- **`no-event` (either target):** the skill's report must show no mention of `run-event-hooks` or
  either hook phase at all, and must return exactly `successful` — proving the code path is
  identical to before `--event` existed, not merely that the (present but unused) `instructions`
  map produced no matches.

## Re-running after a skill edit

1. Re-materialize each of the four combinations (Step 1) into a fresh destination — never reuse a
   previous dry run's worktree.
2. Re-run Steps 2–3 against the edited skill for all four combinations.
3. If a checklist item now fails, the edit introduced a regression — fix it before merging, the
   same way a failing unit test blocks a merge elsewhere in this repo.

No fixture content changes as part of a routine re-run. Fixtures only change if
`workflow-worker`/`workflow-script`'s own `--event` contract changes (e.g. its argument shape or
the outcome-computation rule), in which case update `build_fixture.py` and
`test_build_fixture.py` together and note it in that change's PR.
