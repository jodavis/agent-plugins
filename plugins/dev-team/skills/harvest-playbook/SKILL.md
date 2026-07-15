---
name: harvest-playbook
user-invocable: false
description: >
  Use when turning a validated spec and/or exemplar repos into a reusable playbook.
  Gathers inputs from supplied paths, classifies candidate methodology content via Method
  markers, litmus-test classification, and exemplar diffing, interviews the user, authors a
  vendor-neutral playbook directory, replaces consumed Method markers with provenance links,
  and presents the resulting TODO list.
argument-hint: <spec-path | none> [--exemplar <repo-path>]... [--template-output <path>] --out <playbook-directory> [--name <playbook-name>]
---

Use this skill when:
- A user runs `/harvest` to turn a method that has proven itself (recorded in a spec's Method
  markers, visible in exemplar repos' git history, or both) into a reusable playbook
- An existing playbook needs an update pass because a later instance's build diverged from it

You are gathering durable-artifact inputs, classifying which of their content is reusable
methodology, interviewing the user to confirm candidates and fill gaps, authoring a
vendor-neutral playbook directory, replacing consumed Method markers in the source spec with
provenance links, and presenting the resulting TODO list.

Use the `playbook-contract` skill for: the playbook directory contract, TODO marker semantics,
the Method marker format and lifecycle, the vendor-neutrality rules, and bare-name playbook
resolution. This skill cites those definitions — it does not restate them.

## Steps

### 1 — Gather inputs from the supplied paths

Arguments (accepted as flags per the syntax above, or conversationally — there is no rigid
CLI): `spec-path` (or `none`), zero or more `--exemplar <repo-path>`, an optional
`--template-output <path>`, a required `--out <playbook-directory>`, and an optional
`--name <playbook-name>`.

The user may also state a harvest scope conversationally at this point — for example, "just
pull out the new integration-test dependency strategy" rather than the whole spec's method.
Record it if given; it narrows step 2's candidate-building and step 3's interview to that
scope. If no scope is given here, step 3 asks for it explicitly before working the candidate
list — harvesting the whole artifact is never the assumed default; it could be a part of the
process, some particularly useful template content, or the whole thing.

Before reading anything, enforce the two input-boundary rules:

- **At least one durable-artifact source is required.** `spec-path` must not be `none`, or at
  least one `--exemplar` path must be supplied. If neither is present, tell the user this
  isn't a harvest — it's authoring a playbook from memory — and stop.
- **Detect update mode.** If `--out` already contains a playbook directory (a `SKILL.md`
  present at that path), this is an update pass, not a fresh harvest: read it now and carry it
  forward as the baseline the interview (step 3) proposes changes against. Never overwrite an
  existing playbook directory without going through the interview first.

With the boundary rules satisfied, read every supplied durable artifact:

- The spec at `spec-path` (if not `none`) in full, including its Method markers and its
  permanent `## Tasks` section.
- Each `--exemplar` repo's git history in commit order: the template-stamp commit, strip/replace
  commits, and any commit where an exemplar's choices diverge from another exemplar or from the
  spec's Planned Implementation.
- `--template-output`, if supplied — pristine, unmodified scaffold output, still carrying its
  placeholder tokens.
- Any ADRs or team docs the spec or exemplars reference.
- The existing playbook at `--out`, if update mode was detected above.

### 2 — Build candidate method content

If step 1 captured a harvest scope, keep this candidate-building focused on it — skip sources
clearly outside that scope.

Assemble the candidate list for the interview from four sources:

- **Markers first.** Every Method marker found in the spec seeds a candidate step, carrying
  its rationale verbatim.
- **Litmus-test classification.** Where markers are absent, or where the exemplars carry more
  construction detail than the spec's markers capture, apply the litmus test — "would this be
  copy-pasted into the next similar spec?" — to spec sections, patterns repeated across
  exemplars' git history, and structural choices the exemplars share. Retroactive harvests
  (a spec with zero markers) rely on this source alone and go into the interview (step 3) with
  a thinner candidate list, expecting to ask more.
- **Template-output diffing, for the strip/replace step.** If `--template-output` was
  supplied, diff it against each exemplar's post-strip/replace commit. The tokens that differ
  between the pristine template and the resolved exemplar, and what they resolved to, become
  the candidate strip/replace step.
- **Plan-vs-history divergence mining.** Compare the spec's Planned Implementation against
  what the exemplars' git history actually shows happened, and compare exemplars against each
  other. A place where two exemplars chose differently, or where an exemplar's history departs
  from the plan, is a candidate for the interview to resolve, not a decision to make silently.

### 3 — Interview the user

If step 1 captured no explicit harvest scope, ask first: does the user want the whole method
harvested, a specific process, or particular template content? Use the answer to focus the
rest of this interview — candidates outside that scope are set aside without being treated as
rejected, and their Method markers (if any) are left untouched per step 6.

Work through the candidate list from step 2 with the user, one item at a time:

- Confirm or reject each candidate as a playbook step.
- Where exemplars disagree — including a plan-vs-history divergence found in step 2 — present
  the conflict plainly and ask the user which is canonical. Record the rejected option as a
  documented manual exception in the relevant step rather than discarding it, if the user's
  answer implies it still applies in some cases.
- Ask for rationale the artifacts didn't capture, especially for steps sourced from litmus-test
  classification rather than a marker.
- Catch vendor-neutrality violations as steps are drafted: for any step that leans on
  team-internal shorthand, ask "this step references your <shorthand> — what does it mean in
  plain terms?" and rewrite the step from the answer before moving on.
- If step 1 detected update mode, also confirm which of the existing playbook's steps still
  hold and which this harvest's new evidence should revise.
- If a shared artifact a step depends on doesn't exist yet, ask whether to extract it now or
  record it as a TODO with a manual fallback; do not decide this unilaterally.
- If the user gives no answer to a question, proceed with your own best recommendation instead
  of blocking on it.

### 4 — Author the playbook directory

Write the playbook directory to `--out` per `playbook-contract`'s directory contract:
`SKILL.md` (ordered construction steps, each with a validation gate) and `spec-template.md`,
plus any scripts or assets a step references by relative path. Every step must satisfy
`playbook-contract`'s vendor-neutrality rules — concrete commands, file operations, and
team-artifact references, never a skill name or dev-team vocabulary. Record every
shared-artifact TODO per `playbook-contract`'s TODO marker semantics: the step's manual
fallback stays in place alongside the TODO, and the TODO is never filed as a tracker item.

Name the playbook directory and its `SKILL.md` title from `--name` if it was supplied,
otherwise from what the interview (step 3) settled on.

If step 1 detected update mode, write the merged result — the existing playbook's steps that
still held, revised by whatever the interview changed — rather than starting the directory
over from nothing.

### 5 — Review the authored playbook with the user

Invoke the `spec-discussion` skill against the playbook's `SKILL.md` from step 4, treating it
the same as a spec file: the user reads the authored content and leaves `> **REVIEW:**`
comments anywhere they want a change, resolved one at a time until none remain. Do not proceed
to step 6 until `spec-discussion` reports no outstanding review markers.

### 6 — Replace consumed Method markers with provenance links

For each Method marker whose candidate (from step 2) was confirmed into the authored playbook
(step 4) and survived review (step 5), replace its body in the spec with a single provenance
line, keeping the callout itself so it still reads as a Method marker:

```markdown
> [!NOTE]
> **Method:** see [<playbook-name> — Step <N>](<path-to-playbook>/SKILL.md).
```

The rationale text itself is removed from the spec, not duplicated — it now lives in the
playbook step it fed. Leave any marker whose candidate was rejected in the interview, or that
was not resolved this run, untouched.

### 7 — Present the TODO list

List every TODO recorded in step 4, each restated with its manual fallback so the user can see
at a glance what is followable today versus what remains pending. Do not file any of these
against a tracker — the playbook's own TODO list is the canonical record.
