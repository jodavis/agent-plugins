Summary: Run procedure for the Playbook Harvesting skill dry-run harness — how to materialize
the fixtures and grade a target skill's output against its component checklist.

# Playbook Harvesting: skill dry-run harness

This directory is the fixture set and run procedure for verifying the Testable prose
components introduced by the Playbook Harvesting feature (`_spec_PlaybookHarvesting.md`), per
`missing-test-harness`. It is consumed by three later tasks' dry runs:

| Target skill | Dry-run task |
|---|---|
| `harvest-playbook` | [ADR-319](https://jodasoft.atlassian.net/browse/ADR-319) |
| `spec-first-draft` instance mode | [ADR-321](https://jodasoft.atlassian.net/browse/ADR-321) |
| `spec-task-breakdown` playbook seeding | [ADR-322](https://jodasoft.atlassian.net/browse/ADR-322) |

None of those skills exist yet as of this harness being built — this file documents the
procedure those tasks will follow, so it can be reviewed and re-run unchanged once they land.

## Fixture contents

| Path | Purpose |
|---|---|
| `fixture-spec.md` | Mini-spec with two Method markers and a small Planned Implementation section — the `spec-path` input to a `harvest-playbook` dry run |
| `exemplar-repo-1/`, `exemplar-repo-2/` | Checked-in per-commit snapshots (no `.git` directories) for two sibling service instances (`orders-service`, `billing-service`) stamped from the same template, plus a commit where the two diverge on logging format — the `--exemplar` inputs to a `harvest-playbook` dry run |
| `materialize.py` | Replays an exemplar's `commits.json` manifest into a throwaway git repo on demand |
| `template-output/` | Pristine template-stamp output (unresolved placeholder tokens) — the `--template-output` input, used to derive the strip/replace step by diffing against an exemplar's post-strip/replace commit |
| `fixture-playbook/` | Hand-authored playbook conforming to `playbook-contract` (`SKILL.md`, `spec-template.md`, `dev-team.md` overlay, `service-yaml-schema.md`) — the input to the `spec-first-draft` instance-mode dry run |
| `fixture-instance-spec.md` | Hand-authored instance spec carrying a `> **Playbook:**` header that points at `fixture-playbook/` — the input to the `spec-task-breakdown` seeding dry run |
| `interview-answer-key.md` | Scripted Q&A for the `harvest-playbook` dry run's interview step, plus the "no answer — proceed with your recommendation" fallback rule |
| `test_materialize.py` | Unit tests for `materialize.py` |

## Invocation model: on-demand, not CI

Dry runs in this harness are **run by the implementing or validating agent whenever
`harvest-playbook`, `spec-first-draft`, or `spec-task-breakdown` is edited** — they are not a
CI gate. Two reasons: a headless dry run needs a managed API credential this repo does not
have, and the agent-graded checklist items (see below) are not deterministic enough to make a
reliable automated gate. CI automation of this same procedure is deferred to
[ADR-334](https://jodasoft.atlassian.net/browse/ADR-334); this procedure is written so that
future harness can invoke it unchanged.

## Step 1 — Materialize the exemplar repos

Each exemplar's checked-in snapshots are replayed into a throwaway git repo (never committed
to this repo — always materialize into a location outside version control):

```bash
python3 plugins/dev-team/fixtures/playbook-harvesting/materialize.py \
  plugins/dev-team/fixtures/playbook-harvesting/exemplar-repo-1 /tmp/dry-run/exemplar-repo-1

python3 plugins/dev-team/fixtures/playbook-harvesting/materialize.py \
  plugins/dev-team/fixtures/playbook-harvesting/exemplar-repo-2 /tmp/dry-run/exemplar-repo-2
```

Materializing is idempotent — re-running either command rebuilds the same commit history from
scratch, so a dry run always starts from a clean, reproducible exemplar state. Delete
`/tmp/dry-run/` (or wherever you pointed the output) once the dry run is done; nothing under
it is meant to persist.

Because `harvest-playbook` mutates the spec it is given (replacing consumed Method markers
with provenance links), copy `fixture-spec.md` to the same scratch location before each run
rather than pointing harvest at the checked-in fixture directly:

```bash
cp plugins/dev-team/fixtures/playbook-harvesting/fixture-spec.md /tmp/dry-run/fixture-spec.md
```

## Step 2 — Run the target skill in a clean session

Start a fresh session with **no memory of this harness's authoring context** — a validating
subagent blind to why the fixtures look the way they do, so the run exercises the skill's
prose exactly as a first-time reader would. Give it only:

- the target skill's own instructions,
- the fixture paths from Step 1 (the scratch copies, not the checked-in originals),
- for a `harvest-playbook` run: `interview-answer-key.md`, with the instruction that it must
  role-play the user strictly from the key and answer anything unscripted with exactly
  "no answer — proceed with your recommendation."

Run the target skill against those inputs to completion.

## Step 3 — Grade the output against the component's checklist

Each target component's checklist is authored in `_spec_PlaybookHarvesting.md`'s
["Verifying the Testable prose components"](../../../../_spec_PlaybookHarvesting.md#verifying-the-testable-prose-components)
subsection — this harness does not duplicate those checklists; it only supplies what they're
graded against. Read that subsection alongside the run's output. Split each checklist item
into one of two kinds:

- **Mechanical** — file existence and forbidden-vocabulary greps, listed as commands below.
  Run the command; the checklist item passes or fails exactly on its exit status / match
  count.
- **Judgment-shaped** — e.g. "steps are executable knowledge, not delegation." The validating
  subagent reads the output and decides, citing the specific line(s) that pass or fail the
  item.

### `harvest-playbook` — mechanical checks

Run these against the harvested playbook directory (`<--out>`) and the scratch copy of
`fixture-spec.md` from Step 1:

```bash
# Output conforms to the playbook contract: required files exist.
test -f <playbook-out>/SKILL.md && test -f <playbook-out>/spec-template.md

# Vendor-neutrality: no dev-team vocabulary leaked into the required, vendor-neutral core.
grep -riE "dev-team|spawn|invoke skill|use skill|subagent" <playbook-out>/SKILL.md <playbook-out>/spec-template.md
# (expect no matches; a match fails this checklist item)

# Method markers in the source spec were replaced with provenance links.
grep -c "harvested into" /tmp/dry-run/fixture-spec.md
# (expect a count equal to the number of markers harvest was asked to consume — 2 for the
# fixture spec's two markers)

# TODO markers carry a manual fallback (not a bare TODO with nothing to do until it's resolved).
grep -B2 "TODO" <playbook-out>/SKILL.md
# (agent-graded: confirm the surrounding text states a followable manual fallback, per
# playbook-contract's TODO semantics)
```

Judgment-shaped items to grade by reading the output: steps are executable knowledge rather
than delegation; the strip/replace step is correctly derived from the `template-output/` vs.
exemplar diff; the plan-vs-history divergence (the logging-format split between
`exemplar-repo-1` and `exemplar-repo-2`) surfaces in the playbook or the interview transcript.

### `spec-first-draft` instance mode — checks

```bash
# The draft was written (agent-graded: confirm its sections match fixture-playbook/spec-template.md's
# sections — Domain, Endpoints, Applicable ADRs, Deltas from playbook assumptions).
test -f <draft-instance-spec-path>

# The playbook reference was stamped into the header.
grep -q "^> \*\*Playbook:\*\*" <draft-instance-spec-path>
```

### `spec-task-breakdown` playbook seeding — checks

Run against a breakdown produced from `fixture-instance-spec.md`:

```bash
# TODO manual fallbacks surfaced in the affected task(s) — fixture-playbook/SKILL.md's Step 3
# carries one (extracting validate-service-yaml).
grep -l "validate-service-yaml" <breakdown-output>
```

Judgment-shaped items to grade by reading the output: tasks mirror `fixture-playbook/SKILL.md`'s
three step groupings (stamp, strip/replace, validate); each step's validation gate appears as
an exit criterion in its task, not just prose.

## Re-running after a skill edit

This harness is meant to be re-run every time `harvest-playbook`, `spec-first-draft`, or
`spec-task-breakdown` is edited:

1. Re-materialize both exemplar repos (Step 1) — always from scratch, so a stale throwaway
   repo from a previous run never leaks into the new one.
2. Re-copy `fixture-spec.md` to a fresh scratch location (harvest mutates its input).
3. Re-run Steps 2–3 against the edited skill.
4. If a checklist item now fails, the skill edit introduced a regression — fix it before
   merging, the same way a failing unit test blocks a merge elsewhere in this repo.

No fixture content changes as part of a routine re-run. Fixtures only change if a target
skill's contract changes — for example, `playbook-contract` (ADR-317) revising the required
playbook file names — in which case update the fixtures here and note it in that task's PR.
