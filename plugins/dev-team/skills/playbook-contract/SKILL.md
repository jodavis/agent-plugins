---
name: playbook-contract
user-invocable: false
description: >
  Reference skill defining the normative, vendor-neutral playbook directory contract: the
  directory shape, TODO marker semantics, vendor-neutrality rules, the Method marker
  convention, and bare-name playbook resolution. Cited by `harvest-playbook`, `dev-spec-first-draft`
  instance mode, and `dev-spec-task-breakdown` playbook seeding so all three agree on one shared
  definition instead of drifting apart.
---

Use this skill when:
- You are authoring, reading, or consuming a playbook — a standalone skill directory that
  captures any reusable process discovered while implementing a spec (how to build a family of
  similar components, a testing strategy, a documentation format, or any other repeatable
  process worth reusing, not only component-building) — and need the normative shape of its
  directory, its markers, or its resolution rules
- You are writing `harvest-playbook` (produces playbooks against this contract),
  `dev-spec-first-draft` instance mode (consumes a playbook's `spec-template.md`), or
  `dev-spec-task-breakdown` playbook seeding (consumes a playbook's steps and validation gates)

## Playbooks are skills with a vendor-neutral directory contract

The dependency direction is fixed: **a playbook never knows dev-team exists; dev-team knows how
to read playbooks.** A playbook must be usable by the full dev-team pipeline, by a teammate with
vanilla Claude Code who has not adopted dev-team, and by a human with no agent at all — so
everything in the contract is vendor-neutral. There is no dev-team-specific overlay file; if a
real need for dev-team-specific annotations proves itself through use, add it then rather than
guessing ahead of evidence.

**Directory contract** (normative shape — copy this verbatim; this skill is the single source of
truth for it):

```
<name>/
  SKILL.md           required — neutral ordered steps + validation gates + TODO markers
  spec-template.md   required — instance-spec template
  <scripts, assets>  optional — anything steps reference by relative path
```

- **`SKILL.md` (required)** — ordered construction steps, each with a validation gate. A
  validation gate is a command plus an observable criterion a human can check (e.g. "run `npm
  test` — the new suite passes with 0 failures"), never a vague "make sure it works."
- **`spec-template.md` (required)** — the instance-spec shape: sections and blanks (domain,
  endpoints, applicable-ADR checklist, deltas from playbook assumptions) that any team member
  could fill in a plain text editor, with no dev-team tooling.
- **Scripts and other supporting assets (optional)** — anything a step references by relative
  path (e.g. `post-scaffold.ps1`). Steps that reference these must still describe what the
  asset does in plain terms, per the vendor-neutrality rules below — a script is a convenience,
  not a substitute for the step's own explanation.

### Vendor-neutrality rules

`SKILL.md` steps are **executable knowledge, never delegation**. A step must spell out concrete
commands, file operations, and references to team artifacts (ADRs, scripts) — it must never say
"use skill X" or lean on any dev-team vocabulary a reader without dev-team wouldn't have.

- **Compliant:** "Run `az group create --name <resource-group> --location <region>` to create
  the resource group before deploying. Validate: `az group show --name <resource-group>` returns
  `provisioningState: Succeeded`."
- **Violating:** "Run the usual deploy skill against the pipeline to bring the service up." This
  leans on team-internal shorthand ("the usual deploy skill," "the pipeline") that a reader
  without dev-team context wouldn't understand. The litmus question a harvest interview asks to
  catch this: "this step references your pipeline — what does it mean in plain terms?" A step
  that fails it must be rewritten into the concrete commands and criteria that skill or pipeline
  stage actually performs, with no dev-team vocabulary left in the prose.

### TODO marker semantics

When a step depends on a shared artifact that doesn't exist yet (a common library not yet
extracted, a scaffold script not yet written), the step carries a `TODO` marker recording that
pending work — **and every TODO-marked step must also carry a manual fallback**, so the step
stays followable before the artifact exists. Example: "copy `src/Common/*` from service-three
(TODO: extract into shared package)."

The TODO list in the playbook is the **canonical record** of pending shared-artifact work — it
is never delegated to a tracker inside the playbook itself (projecting TODOs into a work-item
tracker is an explicitly deferred related feature, ADR-332). Resolving a TODO upgrades its step
from "copy from the exemplar" to "install the package / run the script"; a playbook with open
TODOs is shareable and honest, not blocked.

## Method markers capture rationale in flight; playbooks are the product

A **Method marker** is an annotation dropped anywhere in a spec to record a methodology
observation and its rationale, at the moment it is understood — distinct from the playbook
itself, which is the harvested product. The format is a GitHub alert callout:

```markdown
> [!NOTE]
> **Method:** We validate after the scaffold step because service #2's config drift
> wasn't caught until integration.
```

This is deliberately a structurally distinct syntax from `> **Review:**` markers. Review markers
are actionable — resolved and removed. Method markers have the opposite lifecycle: they persist
until harvest. `[!NOTE]` already connotes "informational, not actionable" to agents and renders
as a visually distinct callout to humans, so consumers don't need to memorize an exception to
otherwise-actionable bold-labeled blockquotes.

Markers are hints, not requirements: harvesting works on specs that have none by falling back to
its own classification and a more thorough interview. The litmus test for methodology content —
used identically whether a marker exists or a harvest is working retroactively with no markers
at all — is: **"Would this be copy-pasted into the next similar spec?"**

Markers persist until harvest. After a marker is consumed by harvest, its callout **remains** —
so consumers still recognize it as a Method marker — but its body is replaced with a single
provenance line. The rationale text itself is *not* retained in the spec; it now lives in the
playbook, avoiding a duplicate copy that would drift:

```markdown
> [!NOTE]
> **Method:** harvested into [stand-up-service — Step 3](<path>/SKILL.md).
```

## Bare-name playbook resolution

When a playbook is named without a full path (e.g. `using stand-up-service` rather than a
directory path), resolve it in this order:

1. **Project-local** — `.claude/skills/<name>/` in the current repo.
2. **Installed plugin skill directories** — any plugin-provided skill directory named
   `<name>` (the same discovery surface used by other installed skills).
3. **Ask the user** — on a miss (no match in either location) or an ambiguity (more than one
   match), ask the user for the directory path rather than guessing which one was meant.
