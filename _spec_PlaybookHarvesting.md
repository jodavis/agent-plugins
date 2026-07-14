# Playbook Harvesting

> **Status:** Draft
> **Design doc:** `_doc_PlaybookHarvesting.md` — authored by the final documentation task once
> implementation completes; this spec persists afterward for harvesting
> **Feature-work-item:** [ADR-316](https://jodasoft.atlassian.net/browse/ADR-316)

## Overview

Separates the "what" from the "how" in dev-team specs so that validated methodology can be
codified into reusable **playbooks** — standalone skills that capture how to build a family of
similar components (e.g. a set of microservices): construction order, validation gates, spec
shape, and pointers to shared artifacts. A Method marker convention (a `> [!NOTE]` callout
with a `**Method:**` label) captures methodology rationale while a spec is in flight; a new user-invoked `harvest-playbook` skill
turns that raw material — plus git history of exemplar repos and an interview with the user —
into a vendor-neutral playbook after the user judges the method validated; and a small
consumption hook in `spec-first-draft` lets a later `/spec` run draft a thin "instance spec"
from a named playbook's template. Playbooks never depend on dev-team: they are usable by a
teammate with vanilla Claude Code, or with no agent at all. Because harvest needs its inputs
to survive implementation, this feature also revises the spec lifecycle: specs are no longer
converted into `_doc_*.md` files — they persist, and design documentation is authored from
them by a standard final breakdown task.

## Responsibilities & Boundaries

- **Owns:**
  - The Method marker convention: format, semantics, lifecycle (authored during spec work,
    preserved by `spec-discussion`, consumed and replaced with playbook links by harvest)
  - The revised spec lifecycle: specs persist after implementation instead of being converted
    to `_doc_*.md`; design documentation is authored from the spec by an unconditional final
    breakdown task (see Key Design Decisions)
  - The playbook contract: required vendor-neutral core (`SKILL.md` steps, `spec-template.md`,
    scripts), documented in a new `playbook-contract` knowledge skill
  - The `harvest-playbook` skill and its `/harvest` command: path-agnostic inputs (spec path,
    exemplar repo paths, output directory), classification via the copy-paste litmus test,
    user interview, vendor-neutral authoring rules, TODO markers for pending shared-artifact
    extractions
  - The instance-mode consumption hooks: in `spec-first-draft`, an explicitly named playbook's
    `spec-template.md` replaces the default spec template and the playbook reference is
    stamped into the instance spec's header (`> **Playbook:** <name or path>`); in
    `spec-task-breakdown`, that header reference seeds tasks from the playbook's step
    groupings and folds its validation gates into exit criteria
  - The playbook validation procedure: replay from an exemplar repo's initial commit in a
    clean session, then diff against the finished exemplar
- **Does not own:**
  - The content of any specific playbook (e.g. the microservice playbook) — that is produced
    *by* this feature, in a separate repo, and validated as this feature's acceptance test
  - Playbook hosting — playbooks live in existing marketplaces and skill repos (a `playbooks`
    plugin in this marketplace for personal, generic playbooks; the team's existing shared
    skill repository for team playbooks); this feature only requires that harvest can write
    its output to any given directory. Placement caveat: this marketplace is public-facing,
    so playbooks with work-internal content (team ADRs, internal tooling, the microservice
    playbook itself) belong in the team's repository, never here
  - Shared-artifact extraction work (libraries, scaffolds, post-scaffold scripts) — harvest
    records these as TODO markers in the playbook; performing the extractions is normal
    development work in the target repos
  - Playbook discovery, PR automation, staleness checks, work-item projection of playbook
    TODOs, and promotion tooling — see Related Features
  - The spec pipeline itself (`/spec` flow, readiness review, task breakdown) beyond the
    touchpoints listed under Integrates with
- **Integrates with:**
  - `spec-first-draft` — two edits: the review-pass message teaches the Method marker
    alongside `> **Review:**`, and a new instance-mode step consumes an explicitly named
    playbook's `spec-template.md`
  - `spec-discussion` — one guard rule: Method markers are not review comments; never
    resolve or remove them
  - `spec-task-breakdown` — two edits: appends the unconditional final "Author design
    documentation" task to every breakdown (see Key Design Decisions), and when the spec
    header carries a `> **Playbook:**` reference, seeds tasks and exit criteria from the
    playbook's steps and validation gates
  - `_doc_Projects.md` — its "specs become `_doc_*.md`" sentence is corrected as part of this
    feature's own documentation task
  - `final-sign-off` — one passive note: if the spec contains Method markers, mention that
    `/harvest` is available when the user judges the method proven (never auto-launch). It
    locates the spec with the existing mechanism — `documentation.specs.search` from
    `get-project-configuration`, substituting the `work-item-id` it already receives — so its
    interface is unchanged; if no spec is found, the note is skipped silently
  - `get-project-configuration` — read-only use for the optional work-item projection offer
    (deferred; v1 does not read config at all)
  - `commands/spec.md` — argument-hint gains the `using <playbook>` form; the command forwards
    a detected playbook reference to `spec-first-draft`'s instance mode
  - New files: `skills/harvest-playbook/SKILL.md`, `skills/playbook-contract/SKILL.md`,
    `commands/harvest.md`

## Key Design Decisions

### Method markers capture rationale in flight; playbooks are the product

_Context:_ Specs naturally mix feature content ("what") with methodology ("how"). The
methodology's *rationale* — why this build order, why validate here — surfaces during design
and implementation and evaporates if not written down; retroactive harvesting can recover
steps from artifacts but not the reasoning behind them.

_Decision:_ Two concepts, two names. A **Method marker** is an annotation dropped anywhere in
a spec to record a methodology observation and its rationale, at the moment it is understood.
A **playbook** is the harvested product. The marker format is a GitHub alert callout:

```markdown
> [!NOTE]
> **Method:** We validate after the scaffold step because service #2's config drift
> wasn't caught until integration.
```

The alert form is deliberate: `> **Review:**` markers are pending items — resolved and
removed — and a bold-labeled blockquote has that "actionable" meaning throughout this
pipeline. Method markers have the opposite lifecycle (permanent until harvest), so they get
a structurally distinct syntax rather than relying on every consumer to know an exception.
`[!NOTE]` already connotes "informational, not actionable" to agents and renders as a
visually distinct callout to humans. `spec-discussion` additionally carries an explicit
guard rule — Method markers are not review comments; never resolve or remove them — as
defense in depth.

Markers are hints, not requirements: `harvest-playbook` works on specs that have none
(retroactive mode) by doing its own classification and interviewing the user more. The litmus
test for methodology content, in both modes: *"Would this be copy-pasted into the next
similar spec?"*

Markers persist until harvest. After harvest, each consumed marker's callout remains — so
consumers still recognize it as a Method marker — but its body is replaced with a single
provenance line linking to the playbook section it fed:

```markdown
> [!NOTE]
> **Method:** harvested into [stand-up-service — Step 3](<path>/SKILL.md).
```

The rationale text is not retained in the spec: it now lives in the playbook, and a duplicate
copy would drift. This is the same pattern as task titles becoming work-item links —
provenance survives without cluttering the spec, and the target shape is concrete enough for
the dry-run harness checklist to assert.

_Consequences:_ Capture costs seconds during spec work and requires no tooling. Retroactive
harvests of old specs produce thinner playbooks (missing rationale must come from the user's
memory or be omitted); that is accepted — playbooks harden through update passes when later
instances deviate.

### Specs persist; documentation is authored, not converted

_Context:_ The existing convention — a `_spec_*.md` "becomes" a `_doc_*.md` once
implementation is complete — has two problems. Reviewers sometimes read it as an instruction
for the task at hand and attempt the conversion while later tasks in the same spec are still
open. And harvesting depends on the spec surviving implementation: its Method markers, its
permanent `## Tasks` section, and the divergence between Planned Implementation and what git
history shows actually happened are harvest's primary inputs.

_Decision:_ Specs are never converted or renamed. Instead, `spec-task-breakdown` appends an
**unconditional final agent task — "Author design documentation"** — to every breakdown. Its
exit criteria: create or update the feature's `_doc_*.md` per the project's documentation
configuration, authored *from* the spec (Overview, Responsibilities & Boundaries, and Key
Design Decisions carry over; the task breakdown, Method markers, and planned-vs-actual deltas
do not), and flip the spec's status line to `> **Status:** Implemented — retained for
harvesting`. The user may delete the task from a breakdown where no architecture doc is
warranted; the breakdown never omits it silently, so the decision is always visible.
Individual tasks additionally carry doc-update exit criteria where they touch *existing*
architecture docs — ordinary change hygiene, added only where the breakdown sees a real
collision rather than as boilerplate on every task.

The spec header template in `spec-first-draft` changes from "**Will become:** `_doc_X.md` once
implementation is complete" to a "**Design doc:**" line declaring that the doc is authored by
the final documentation task and the spec persists for harvesting (this spec's own header
models the new form). Existing `_spec_*.md` files in this repo still carrying the old header
are retrofitted to the new form as a one-time task in this feature's breakdown; specs in
other projects are updated opportunistically when next touched. Harvested-or-deleted is
thereafter the user's call, on their schedule.

_Consequences:_ The reviewer misread is eliminated at its source. Specs remain available as
harvest input indefinitely. Documentation becomes one coherent authoring pass with full
hindsight rather than a mechanical rename; the cost is a standing final task the user
occasionally deletes as unwarranted.

### Playbooks are skills with a vendor-neutral contract

_Context:_ A playbook must serve three consumers: the full dev-team pipeline, a teammate with
vanilla Claude Code who has not adopted dev-team, and a human with no agent at all. Team
adoption depends on the playbook being evaluable and usable as a plain document.

_Decision:_ The dependency direction is fixed: **a playbook never knows dev-team exists;
dev-team knows how to read playbooks.** A playbook is a skill directory with:

- **Required, vendor-neutral core:**
  - `SKILL.md` — ordered construction steps with validation gates. Steps are executable
    knowledge, never delegation: concrete commands, file operations, and references to team
    artifacts (ADRs, scripts) — never "use skill X" or any dev-team vocabulary. Validation
    gates are commands plus observable criteria a human can check.
  - `spec-template.md` — the instance-spec shape: sections and blanks (domain, endpoints,
    applicable-ADR checklist, deltas from playbook assumptions) that any team member could
    fill in a text editor.
  - Scripts and other supporting files as needed (e.g. `post-scaffold.ps1`).

There is no dev-team-specific overlay file: if a real need for dev-team-specific annotations
proves itself through use, it is added then rather than guessed ahead of evidence.

The contract lives in a new `playbook-contract` knowledge skill (the `component-taxonomy`
pattern) that both `harvest-playbook` and the `spec-first-draft` hook cite, so the two sides
cannot drift apart.

_Consequences:_ Prose forbidden from delegating to skills must spell out what those skills
know — which makes playbooks more concrete and more durable. A playbook repo needs no
dependency on the dev-team plugin.

### Harvest is path-agnostic; multi-repo is an argument list, not an architecture

_Context:_ The driving scenario is a multi-repo microservice family: exemplar services in
separate repositories, the playbook destined for a shared team repository. A harvest design
that assumed "playbook lives in this repo's `.claude/skills/`" would require a retrofit within
weeks.

_Decision:_ `harvest-playbook` takes every location as an explicit argument: the spec path,
zero or more exemplar repo paths (local clones), optionally a path to pristine template output
(e.g. what a Backstage template stamps out, for deriving strip/replace steps by diffing), and
the output directory. It writes the playbook directory to the output path and stops —
committing, PR-ing, or publishing the result is the user's act. Local piloting is the same
skill with the output pointed at the current repo.

Two input-boundary rules complete the argument contract. **At least one durable-artifact
source (a spec or an exemplar repo) is required** — with neither, "harvest" is just authoring
a skill from memory, which needs no harvest machinery; the skill says so and stops. And **an
existing playbook directory at the output path means update mode**, never a blind overwrite:
harvest reads the existing playbook as prior state and proposes changes through the interview
— this is the designed "update pass" that deviations in later instances feed (see Data Flow),
not an error case.

_Consequences:_ No repo-topology knowledge, no configuration dependency, no distinction
between personal and team use inside the skill. The cost is manual path-wrangling per
invocation, acceptable for an explicitly user-triggered activity.

### Harvest authors prose but only proposes code; playbook TODOs are canonical

_Context:_ Methodology and templates are cheap to author in-session. Shared artifacts
(extracting a common library, building a scaffold script) are real development work needing
tests and review — and in the multi-repo case it is not even clear whose tracker would own the
task. Meanwhile the playbook's audience may lack access to any particular tracker.

_Decision:_ When harvest identifies a shared-artifact candidate, it records a TODO marker in
the playbook step, and the step always carries a manual fallback so it remains followable
before the artifact exists — e.g. *"copy `src/Common/*` from service-three (TODO: extract into
shared package)."* The TODO list in the playbook is the canonical record. Resolving TODOs
upgrades steps from "copy from the exemplar" to "install the package / run the script"; a
playbook with open TODOs is shareable and honest, not blocked. Work-item projection ("file
these as tracker items?") is deferred to Related Features.

_Consequences:_ Harvest stays read-and-author-only, matching the trust model of the rest of
the pipeline. Every consumer sees the pending work regardless of tracker access. Long-lived
TODOs (e.g. "contribute a team Backstage template upstream") are legitimate.

### Explicit trigger, explicit naming — no discovery in v1

_Context:_ The user decides when a method has proven itself worth codifying; premature
harvesting codifies guesses. Similarly, automatic playbook-to-project matching needs a
configuration schema and matching semantics that are better designed after real playbooks
exist.

_Decision:_ Harvest runs only via the user-invoked `/harvest` command; `final-sign-off` may
passively note that Method markers exist, never launch a harvest. Consumption is by explicit
naming: the user tells `/spec` which playbook to use (a path or an installed skill name).
`spec-first-draft` reads that playbook's `spec-template.md` in place of the default template,
uses its step list as input to the Component Breakdown, and stamps the reference into the
instance spec's header as `> **Playbook:** <name or path>`. Downstream consumers read the
reference from the spec header rather than requiring the user to re-name it:
`spec-task-breakdown` seeds tasks from the playbook's step groupings, folds validation gates
into exit criteria (they are already commands plus observable criteria — the form exit
criteria take), and surfaces TODO manual fallbacks in the affected tasks. The header stamp is
also the natural hook for the deferred staleness checks. If no playbook is named, nothing changes about
today's flow.

_Consequences:_ Zero configuration surface in v1. Config-based discovery
(`get-project-configuration` gaining a `playbooks` section) is deferred until harvested
playbooks exist to inform its design.

### Harvest inputs: artifacts plus interview, never transcripts

_Context:_ Fresh harvests could theoretically mine session transcripts; retroactive harvests
have no transcripts. Two input models would mean two code paths, and transcripts are noisy.

_Decision:_ Harvest reads durable artifacts only — the spec (including its permanent `## Tasks`
section), Method markers, git history of the exemplar repos (commit order, early
strip/replace commits, divergence between plan and reality), ADRs and team docs, template
output — and conducts a structured interview with the user. Interview intensity scales
inversely with marker coverage: markers seed the candidate list and carry rationale; absent
markers, harvest builds the candidate list itself and asks more. Where exemplars disagree,
harvest presents the conflict and the user rules on which is canonical.

_Consequences:_ One code path for fresh and retroactive harvests. The user is always in the
loop, which fits the "harvest when I judge it proven" trigger model.

### Validation by replay-and-diff

_Context:_ A playbook's quality claim is "a cold reader could stand up the next instance from
this." That is testable without waiting for a real next instance.

_Decision:_ The standard validation procedure, documented as the final section of
`harvest-playbook`: create a branch of an exemplar repo at its initial commit (a second clone
or worktree, so the finished exemplar remains on disk for the TODO fallbacks to reference);
run a clean session given only the playbook; diff the result against the finished exemplar at
HEAD. Diff gaps are the playbook's blind spots — under-specified steps and uncaptured
decisions — which feed a harvest update pass. The session must be blind to the finished code
except through the playbook's own references.

_Consequences:_ Reusable acceptance mechanism for any playbook, not just the first. This
feature's own exit criterion uses it (see Tasks): the real microservice playbook, harvested
from the three existing services, validated by replay-and-diff.

## Component Breakdown

| Component | Type | Responsibility | Depends on |
|---|---|---|---|
| `playbook-contract` (new skill) | Wrapper | Defines the playbook contract, TODO marker semantics, and Method marker convention — definitional prose, no procedure | — |
| `harvest-playbook` (new skill) | Testable | The harvest procedure: gather inputs from paths, classify via litmus test, interview, author vendor-neutral playbook, replace Method markers with links, document replay-and-diff validation | `playbook-contract`, skill dry-run harness |
| `commands/harvest.md` (new) | Wrapper | Thin dispatcher: argument hints, invokes `harvest-playbook` | `harvest-playbook` |
| `commands/spec.md` playbook argument (edit) | Wrapper | Argument-hint documents `using <playbook>`; forwards a detected playbook reference to `spec-first-draft` instance mode | — |
| `spec-discussion` Method-marker guard (edit) | Wrapper | One rule: Method markers are not review comments; never resolve or remove | `playbook-contract` |
| `spec-first-draft` marker authoring note (edit) | Wrapper | Review-pass message teaches the Method marker callout alongside `> **Review:**` | `playbook-contract` |
| `spec-first-draft` header wording (edit) | Wrapper | Spec header template declares the derived "Design doc" instead of "Will become" conversion | — |
| `spec-task-breakdown` documentation task (edit) | Wrapper | Appends the unconditional final "Author design documentation" task; adds doc-update exit criteria to tasks touching existing docs | — |
| `spec-first-draft` instance mode (edit) | Testable | When a playbook is explicitly named: read its `spec-template.md` and step list, draft the thin instance spec, stamp the `> **Playbook:**` header reference | `playbook-contract`, skill dry-run harness |
| `spec-task-breakdown` playbook seeding (edit) | Testable | When the spec header carries a `> **Playbook:**` reference: seed tasks from step groupings, fold validation gates into exit criteria, surface TODO manual fallbacks | `playbook-contract`, skill dry-run harness |
| `final-sign-off` harvest note (edit) | Wrapper | If the spec contains Method markers, mention `/harvest` availability | — |
| Skill dry-run harness (new, `missing-test-harness` line item) | Testable | Fixtures (synthetic mini-spec with Method markers; tiny fake exemplar repos with scripted git history) plus per-component observable-outcome checklists and a run procedure | — |

Skill prose is Testable where it carries procedure with branching judgment (harvest, instance
mode, breakdown seeding) and Wrapper where it is definitional or a single-rule edit, per
`component-taxonomy`.

### Verifying the Testable prose components

Per `component-taxonomy`, Testable names a tier of risk, not a mechanism; skill prose is
verified by the mechanism that fits. Here that mechanism is **fixture-driven dry runs**: a
clean session (a validating subagent, blind to authoring context) runs the skill against
checked-in fixtures and grades the output against a per-component checklist of observable
outcomes.

- `harvest-playbook` — run against the fixture spec and exemplar repos: output directory
  conforms to the playbook contract (required files exist); Method markers in the fixture
  spec were replaced with playbook links; TODO markers carry manual fallbacks; and
  vendor-neutrality holds — mechanically checkable by grepping the core files for forbidden
  vocabulary (dev-team skill names, "spawn", "invoke skill"). Judgment-shaped criteria
  ("steps are executable knowledge, not delegation") are graded by the validating agent
  against the checklist. The interview step is exercised via a scripted answer key in the
  fixture set: the validating subagent role-plays the user strictly from the key, answering
  unscripted questions with "no answer — proceed with your recommendation," so runs stay
  reproducible.
- `spec-first-draft` instance mode — given a fixture playbook: the draft uses
  `spec-template.md`'s sections in place of the default template and stamps the
  `> **Playbook:**` header reference.
- `spec-task-breakdown` playbook seeding — given a fixture instance spec: tasks mirror the
  playbook's step groupings, validation gates appear in exit criteria, TODO manual fallbacks
  surface in the affected tasks.

The discipline is checklist-first: each component's checklist is authored before its skill
prose (red), then the skill is written or revised until the dry run passes (green). Fixtures
and checklists persist in the repo so future edits re-run the same dry runs. Because no such
harness exists yet, building it is its own line item above, per `missing-test-harness` —
not an implementation-time improvisation.

Dry runs are **on-demand**, not CI-automated: they are run by the implementing or validating
agent whenever these skills are edited. CI automation would require headless agent sessions
with a managed API credential and a recurring per-run token cost, and the agent-graded
criteria are not deterministic enough to make a reliable gate — deliberately deferred (see
Related Features). The run procedure is written so a future CI harness could invoke it
unchanged.

The feature-level acceptance tests — the retroactive-harvest shakeout of an existing spec and
the replay-and-diff validation of the real microservice playbook — sit above these dry runs
as the E2E layer, in the same relationship E2E scenarios have to unit tests elsewhere in the
pipeline.

## Planned Implementation

### Interfaces

**`/harvest` command → `harvest-playbook` skill arguments:**

```
/harvest <spec-path | none> [--exemplar <repo-path>]... [--template-output <path>]
         --out <playbook-directory> [--name <playbook-name>]
```

Argument semantics (positional/flag syntax is illustrative; the skill accepts these as
conversational arguments too):

- `spec-path` — the spec to harvest from; `none` for purely exemplar-driven harvests
- `--exemplar` — repeatable; local clone paths of instances built with the method
- `--template-output` — pristine scaffold output for strip/replace derivation by diff
- `--out` — directory the playbook skill directory is written into (a local clone of the
  hosting repo — e.g. this marketplace's `playbooks` plugin or the team's shared skill
  repository — or the current repo for local piloting); an existing playbook directory here
  triggers update mode (see Key Design Decisions), never a blind overwrite
- `--name` — kebab-case playbook name; derived from the spec/interview when omitted

**`spec-first-draft` instance-mode input:** a playbook reference — a directory path or an
installed skill name — supplied by the user in the `/spec` invocation (`using <playbook>`,
forwarded by `commands/spec.md`) or conversation. Bare-name resolution is defined in
`playbook-contract`: project-local `.claude/skills/<name>/` first, then installed plugin
skill directories; on a miss or ambiguity, ask the user for the directory path rather than
guessing.

**Playbook directory contract** (normative definition lives in `playbook-contract`):

```
<name>/
  SKILL.md           required — neutral ordered steps + validation gates + TODO markers
  spec-template.md   required — instance-spec template
  <scripts, assets>  optional — anything steps reference by relative path
```

### Key Files

- `plugins/dev-team/skills/playbook-contract/SKILL.md` — knowledge skill; contract above,
  Method marker convention, TODO semantics, vendor-neutrality rules with examples of
  compliant vs. delegating step prose
- `plugins/dev-team/skills/harvest-playbook/SKILL.md` — stepwise procedure: (1) read inputs
  from supplied paths; (2) build candidate method content — markers first, else litmus-test
  classification, plus template-output/exemplar diffing for scaffold-correction steps and
  plan-vs-history divergence mining; (3) interview: confirm candidates, resolve exemplar
  conflicts, capture missing rationale, catch vendor-neutrality violations ("this step
  references your pipeline — what does it mean in plain terms?"); (4) author the playbook
  directory per contract; (5) replace consumed Method markers with playbook links; (6) present
  the TODO list and the replay-and-diff validation procedure
- `plugins/dev-team/commands/harvest.md` — command wrapper
- Edits: `spec-discussion` (guard), `spec-first-draft` (marker note + instance mode),
  `final-sign-off` (passive note)

### Data Flow

1. **Capture:** during any spec's lifecycle, user or agent drops Method marker callouts;
   `spec-discussion` preserves them; implementation proceeds normally.
2. **Harvest:** after validation, user runs `/harvest` with paths → skill mines spec, markers,
   exemplar git histories, template diff → interview → playbook directory written to `--out`
   → markers in the source spec replaced with links → user commits/PRs the playbook wherever
   it lives.
3. **Consume:** user runs `/spec ... using <playbook>` → instance mode drafts a thin spec from
   `spec-template.md` and stamps `> **Playbook:**` into its
   header → normal refinement and readiness review follow → `spec-task-breakdown` reads the
   header reference and seeds tasks and exit criteria from the playbook's steps and validation
   gates → deviations discovered during the build become input to a harvest update pass
   (re-run `/harvest` over the updated state).

## Related Features

| Feature | Scope |
|------|-------|
| (this feature — [ADR-316](https://jodasoft.atlassian.net/browse/ADR-316)) | Method markers, path-agnostic harvest, playbook contract, explicit-naming instance mode, replay-and-diff validation |
| [Playbook discovery](https://jodasoft.atlassian.net/browse/ADR-329) | `get-project-configuration` gains a `playbooks` section mapping component families to playbooks; `spec-first-draft` auto-detects applicability instead of requiring explicit naming |
| [Harvest PR output](https://jodasoft.atlassian.net/browse/ADR-330) | Harvest optionally opens a PR against the playbook's hosting repo instead of writing to a local directory |
| [Playbook staleness checks](https://jodasoft.atlassian.net/browse/ADR-331) | Readiness review verifies a consumed playbook's references (paths, scripts, ADRs) still hold; deviation reporting feeds update passes |
| [Work-item projection](https://jodasoft.atlassian.net/browse/ADR-332) | Optional "file these as tracker items?" offer for playbook TODOs, via the work-tracking adapter machinery |
| [Promotion tooling](https://jodasoft.atlassian.net/browse/ADR-333) | De-specialization pass moving a project-local playbook to a shared plugin/marketplace (single-repo scenario only; multi-repo playbooks are born shared) |
| [CI-automated skill dry runs](https://jodasoft.atlassian.net/browse/ADR-334) | Run the dry-run harness headlessly on PRs touching skill prose. Known constraints: managed API-key authentication (repo secret), per-run token budgets with Console usage alerts, and handling nondeterminism in agent-graded criteria |

## Open Questions

- [ ] None — all key decisions were resolved in pre-spec discussion.

## Related Docs

- `_doc_Projects.md` — repository layout and plugin conventions
- `_spec_TddForImplementation.md` — precedent: methodology harvested into skills by hand; also
  the source of the component taxonomy used in this spec
- `plugins/dev-team/skills/spec-first-draft/SKILL.md`, `spec-discussion/SKILL.md`,
  `final-sign-off/SKILL.md` — the three integration touchpoints
- `plugins/dev-team/skills/component-taxonomy/SKILL.md` — the knowledge-skill pattern
  `playbook-contract` follows
- [GitHub Markdown alert syntax](https://github.com/orgs/community/discussions/16925) — the
  `> [!NOTE]` callout used by Method markers; degrades to a plain blockquote (marker text
  still visible) on non-GitHub renderers

## Tasks

### Agent tasks

#### 1. [Author `playbook-contract` knowledge skill](https://jodasoft.atlassian.net/browse/ADR-317)

Create the normative knowledge skill defining the playbook contract, following the
`component-taxonomy` pattern.

- [ ] `plugins/dev-team/skills/playbook-contract/SKILL.md` defines: the directory
      contract (required `SKILL.md` + `spec-template.md`; optional supporting scripts),
      TODO marker semantics with mandatory manual fallbacks, and the
      vendor-neutrality rules with compliant vs. violating step-prose examples
- [ ] The Method marker convention is specified: `> [!NOTE]` / `**Method:**` format, lifecycle
      (persistent until harvest, then body replaced with a provenance link), and the
      post-harvest target shape
- [ ] Bare-name playbook resolution is specified: project-local `.claude/skills/<name>/`,
      then installed plugin skill directories, else ask the user for a path

#### 2. [Build the skill dry-run harness](https://jodasoft.atlassian.net/browse/ADR-318)

Create the fixtures and run procedure that verify the Testable prose components, per
`missing-test-harness`. Requires Task 1 ([ADR-317](https://jodasoft.atlassian.net/browse/ADR-317))
— fixtures conform to the contract and marker format it defines.

- [ ] Fixture mini-spec exists with Method markers (new callout format) and a small
      Planned Implementation section
- [ ] Two tiny fixture exemplar repos exist with scripted git history (template stamp,
      strip/replace commits, divergent choices between the two exemplars), persisted as
      checked-in content plus a setup script that materializes the throwaway git repos on
      demand each run — no nested `.git` directories are committed
- [ ] A fixture pristine-template-output directory exists for strip/replace derivation
- [ ] A hand-authored fixture playbook directory (conforming to `playbook-contract`) exists
      for Task 5's instance-mode dry run
- [ ] A hand-authored fixture instance spec with a `> **Playbook:**` header exists for
      Task 6's seeding dry run
- [ ] A scripted interview answer key is part of the fixture set: the validating subagent
      role-plays the user strictly from the key, answering unscripted questions with "no
      answer — proceed with your recommendation," keeping dry runs reproducible
- [ ] The run procedure is documented: a validating subagent, blind to authoring context,
      runs a target skill against the fixtures and grades output against that component's
      checklist; mechanical assertions (file existence, forbidden-vocabulary grep) are
      listed as commands
- [ ] The harness is re-runnable: fixtures and procedure are checked in, with instructions
      for re-running after future skill edits
- [ ] The run procedure documents its on-demand invocation model (agent-run when skills are
      edited; not CI-automated — see Related Features for the deferred CI variant)

#### 3. [Implement `harvest-playbook` skill and `/harvest` command](https://jodasoft.atlassian.net/browse/ADR-319)

The core harvest procedure and its thin command dispatcher. Requires Tasks 1–2
([ADR-317](https://jodasoft.atlassian.net/browse/ADR-317),
[ADR-318](https://jodasoft.atlassian.net/browse/ADR-318)).

- [ ] Checklist for the dry run is authored before the skill prose (red), covering: output
      conforms to the playbook contract; Method markers in the source spec replaced with
      provenance links; TODO markers carry manual fallbacks; vendor-neutrality grep passes;
      steps are executable knowledge (agent-graded); a strip/replace step is correctly
      derived from the template-output diff; a plan-vs-history divergence mined from the
      exemplars surfaces in the playbook or interview
- [ ] `harvest-playbook` implements the six-step procedure (gather from paths → candidate
      method content via markers/litmus test/exemplar diffing → interview → author playbook →
      replace markers → present TODO list and replay-and-diff procedure)
- [ ] Argument contract enforced: at least one durable-artifact source required; existing
      playbook directory at the output path triggers update mode, never blind overwrite
- [ ] `commands/harvest.md` dispatches to the skill with documented argument hints
- [ ] Given the fixture spec, exemplar repos, and pristine template output, When
      `harvest-playbook` runs against them in a clean session (interview via the fixture
      answer key), Then the dry-run checklist passes — including the derived strip/replace
      step and the surfaced divergence

Deliberately one task despite its size: it is one skill file and one Testable component. If a
session runs long, the checklist-first structure provides a natural intermediate commit point
(checklist and fixtures wiring first, procedure prose second).

#### 4. [Adopt Method marker and header conventions across spec-pipeline skills](https://jodasoft.atlassian.net/browse/ADR-320)

The small Wrapper edits that teach the pipeline the new conventions. Requires Task 1
([ADR-317](https://jodasoft.atlassian.net/browse/ADR-317)) — the conventions these edits
reference are defined there.

- [ ] `spec-discussion` gains the guard rule: Method markers are not review comments; never
      resolve or remove them
- [ ] `spec-first-draft`'s review-pass message teaches the Method marker callout alongside
      `> **Review:**`
- [ ] `spec-first-draft`'s header template uses the `> **Design doc:**` line in place of
      "**Will become:**"
- [ ] `final-sign-off` adds the passive note: locate the spec via `documentation.specs.search`
      with its `work-item-id`; if the spec contains Method markers, mention `/harvest`
      availability; skip silently when no spec is found
- [ ] Existing `_spec_*.md` files in this repo are retrofitted to the new header form

#### 5. [Implement instance mode in `spec-first-draft` and `/spec` forwarding](https://jodasoft.atlassian.net/browse/ADR-321)

Consumption at drafting time. Requires Tasks 1–2
([ADR-317](https://jodasoft.atlassian.net/browse/ADR-317),
[ADR-318](https://jodasoft.atlassian.net/browse/ADR-318)).

- [ ] Checklist for the dry run is authored before the skill prose (red)
- [ ] `commands/spec.md` documents the `using <playbook>` argument form and forwards a
      detected playbook reference to `spec-first-draft`
- [ ] Instance mode: resolve the playbook reference (per `playbook-contract`), read
      `spec-template.md` in place of the default template, stamp `> **Playbook:**` into the
      instance spec header
- [ ] Given a fixture playbook, When `/spec` runs in instance mode in a clean session, Then
      the draft uses the template's sections and carries the header stamp

#### 6. [Implement playbook seeding and the documentation task in `spec-task-breakdown`](https://jodasoft.atlassian.net/browse/ADR-322)

Consumption at breakdown time, plus the spec-lifecycle change (both edits live in this one
skill file). Requires Tasks 1–2
([ADR-317](https://jodasoft.atlassian.net/browse/ADR-317),
[ADR-318](https://jodasoft.atlassian.net/browse/ADR-318)).

- [ ] Checklist for the seeding dry run is authored before the skill prose (red)
- [ ] When the spec header carries `> **Playbook:**`: tasks seed from the playbook's step
      groupings, validation gates fold into exit criteria, TODO manual fallbacks surface in
      affected tasks
- [ ] Every breakdown appends the unconditional final "Author design documentation" task
      (exit criteria per the "Specs persist" design decision, including flipping the spec
      status line); the task is never omitted silently
- [ ] Tasks touching existing architecture docs gain doc-update exit criteria only where the
      breakdown sees a real collision
- [ ] Given a fixture instance spec, When the breakdown runs in a clean session, Then tasks
      mirror step groupings, gates appear as exit criteria, and the final documentation task
      is present

#### 7. [Retroactive-harvest shakeout](https://jodasoft.atlassian.net/browse/ADR-323)

Validate the no-markers path by harvesting an existing spec from this repo (candidate:
`_spec_TddForImplementation.md`), with the user in the interview loop. Output pointed at a
local scratch directory — this playbook is a test artifact, not a deliverable. Requires
Task 3 ([ADR-319](https://jodasoft.atlassian.net/browse/ADR-319)).

- [ ] Given a completed spec with no Method markers, When `/harvest` runs with the user
      answering interview questions, Then a playbook directory is produced that conforms to
      the contract and passes the vendor-neutrality grep
- [ ] `harvest-playbook` is revised per the findings (gaps in the harvest procedure, awkward
      interview turns) within this task — the revisions land in this task's PR, not as
      unscoped follow-up; anything unaddressable without team input is recorded in
      [ADR-327](https://jodasoft.atlassian.net/browse/ADR-327)

#### 8. [Add a `playbooks` plugin to this marketplace](https://jodasoft.atlassian.net/browse/ADR-324)

Hosting for personal, generic playbooks (public-facing — work-internal playbooks go to the
team's shared skill repository instead).

- [ ] `plugins/playbooks/` exists with its own `.claude-plugin/plugin.json` and an empty
      skills directory, registered in `.claude-plugin/marketplace.json`
- [ ] `_doc_Projects.md` layout table gains the new plugin (folded into Task 9's doc pass if
      landed together)

#### 9. [Author design documentation (final task)](https://jodasoft.atlassian.net/browse/ADR-325)

Per this spec's own lifecycle rule — unconditional, last among the agent tasks. Requires
Tasks 1–8. The feature's acceptance test (H2/H3) may still be outstanding when this task
runs, so the status flip here is to an acceptance-pending form; H3 performs the final flip.

- [ ] `_doc_PlaybookHarvesting.md` authored from this spec (Overview, Responsibilities &
      Boundaries, Key Design Decisions carry over; tasks, markers, and planned-vs-actual
      deltas do not)
- [ ] `_doc_Projects.md`'s "specs become `_doc_*.md`" sentence corrected to the new lifecycle
- [ ] This spec's status line flipped to `> **Status:** Implemented — acceptance pending
      ([ADR-327](https://jodasoft.atlassian.net/browse/ADR-327),
      [ADR-328](https://jodasoft.atlassian.net/browse/ADR-328))`

### Human-required tasks

#### H1. [Confirm the team's shared skill repository as playbook host](https://jodasoft.atlassian.net/browse/ADR-326)

The `stand-up-service` playbook will live in the team's existing shared skill repository —
no new repo is created.

- [ ] Write access confirmed and the repository's naming/layout conventions identified
- [ ] A playbook directory (per `playbook-contract`) fits the repository's structure, or the
      accommodation needed is agreed with the team

#### H2. [Harvest the microservice playbook (user-led, agent-assisted)](https://jodasoft.atlassian.net/browse/ADR-327)

The real harvest: run `/harvest` across services #1, #2, and #3 (local clones) plus the
Backstage template output, output pointed at a local clone of the team's shared skill
repository. Requires Task 3, Task 7, and H1.

- [ ] Given the three service repos and template output, When `/harvest` runs with the user
      ruling on exemplar conflicts, Then the `stand-up-service` playbook is produced in the
      shared skill repository clone with strip/replace steps, ADR-referencing construction
      steps, validation gates, `spec-template.md`, and TODO markers for pending extractions
- [ ] The user judges the interview questions worth their time (qualitative gate on the
      harvest UX)

#### H3. [Replay-and-diff validation (user-led)](https://jodasoft.atlassian.net/browse/ADR-328)

The feature's acceptance test. Requires H2.

- [ ] Given a branch of service #3 at its initial commit (separate clone/worktree) and a
      clean session given only the playbook, When the session follows the playbook, Then the
      diff against service #3 at HEAD is reviewed and each gap is classified as playbook
      blind spot (feeds an update pass) or acceptable instance variation
- [ ] The playbook passes the cold-reader bar: the session completed the strip/replace and
      construction steps without information the playbook failed to provide
- [ ] This spec's status line flipped to `> **Status:** Implemented — retained for
      harvesting` (the feature's acceptance is now met)

### Related feature placeholders

Feature-work-items created (Epics, no parent):

- **[ADR-329 — Playbook discovery](https://jodasoft.atlassian.net/browse/ADR-329)** —
  `get-project-configuration` gains a `playbooks` section; `spec-first-draft` auto-detects
  applicability
- **[ADR-330 — Harvest PR output](https://jodasoft.atlassian.net/browse/ADR-330)** — harvest
  optionally opens a PR against a playbook's hosting repo instead of writing locally
- **[ADR-331 — Playbook staleness checks](https://jodasoft.atlassian.net/browse/ADR-331)** —
  readiness review verifies a consumed playbook's references still hold
- **[ADR-332 — Work-item projection](https://jodasoft.atlassian.net/browse/ADR-332)** —
  optional "file these as tracker items?" offer for playbook TODOs
- **[ADR-333 — Promotion tooling](https://jodasoft.atlassian.net/browse/ADR-333)** —
  de-specialization pass moving a project-local playbook to a shared plugin
- **[ADR-334 — CI-automated skill dry runs](https://jodasoft.atlassian.net/browse/ADR-334)** —
  run the dry-run harness headlessly on PRs touching skill prose (managed API key, token
  budgets, grading nondeterminism)
