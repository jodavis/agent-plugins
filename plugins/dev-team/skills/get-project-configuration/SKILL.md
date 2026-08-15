---
name: get-project-configuration
user-invocable: false
description: >
  Use when a skill needs project-specific configuration (work tracking, documentation
  conventions, developer standards, git-repo conventions). Merges the shipped default with
  machine- and project-level YAML overrides and returns the result as JSON.
---

Use this skill when:
- You need to know how this project tracks work items, where it keeps documentation, which
  files define its coding standards, or its git branch/commit/PR conventions

## Getting the merged configuration

`<skill-dir>` refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is
not an environment variable.

```bash
python3 "<skill-dir>/scripts/merge_config.py"
```

Prints the merged configuration as JSON to stdout and exits 0. On failure (malformed YAML,
no repo root found) it prints `Error: ...` to stderr and exits non-zero — stop and report the
error rather than guessing at configuration.

## Interpreting the merged configuration

### null values

A key that comes back `null` means a project deliberately opted out of that section's shipped
default — treat it as "explicitly none," not as "unconfigured." 

### Path-like values

Any path-like value anywhere in the merged config (e.g. `documentation.architecture.location`, a
`developer-standards` filename) is relative to the repo root, **except** a value starting with
`~`, which is relative to the user's home directory. This is a general rule for the whole
document, not a per-field lookup.

### `developer-standards` — filename → description map

Any entry in this list is expected to exist: if it's missing,
don't block on it, but note it — the project's own config is pointing at something that isn't
there.

### `work-tracking` — map keyed by provider name, or `null`

**If `work-tracking` is `null` or an empty map, this project has no issue tracker configured.**
Any step — in this skill's callers or anywhere else — that would read or update a work item
(looking up an issue, transitioning status, syncing a description) must be skipped outright.
Do not guess a provider, and do not ask the user for a ticket key "just in case." Skills that
depend on work-tracking document their own no-tracker fallback (typically: ask the user
directly, or state that work-item syncing is skipped).

When populated, each key names a provider and dispatches to an adapter skill:

| key | Adapter skill |
|---|---|
| `jira` | `work-with-Jira-tasks` |
| `github` | `work-with-GitHub-issues` |

An unrecognized key is a configuration error — surface it clearly rather than silently ignoring
that provider. Each provider's value may carry `issue-key-pattern` (a regex identifying its
work-item IDs), `recognize-patterns` (a list of alternate regexes a user might type instead of
the canonical ID), and named item-type blocks, alongside their `type`, `replace-description-when`,
and `update-description-when` fields.

Two item-type block names are fixed, well-known keys — every skill in this plugin refers to them
by these names rather than by the tracker's own terminology (e.g. Jira's "Epic"/"Task"), since
that terminology varies by tracker and by project:

- **`task-work-item`** — an individual, concretely-scoped piece of work; sized to roughly one PR.
- **`feature-work-item`** — an overall goal or container that groups multiple task-work-items
  (e.g. a Jira Epic).

Other item-type blocks (e.g. `bug-item`) are free-form — a project can add as many as it needs,
keyed however it likes, for item types that don't participate in the feature/task hierarchy.
`type` on any block records the tracker's real name for that type (e.g. `Epic`, `Task`, `Issue`)
— skills needing to create or recognize an issue of a given kind read `type` from the matching
block rather than hardcoding a tracker-specific name.

### `documentation`

- `format` — the file format shared by all three categories below (e.g. `Markdown`).
- `architecture` — post-implementation docs (written by `write-repo-documentation` once a
  feature ships).
- `specs` — pre-implementation PM-style design docs (written by `design-first-draft`; problem,
  proposed solution, observable behavior — no implementation detail).
- `dev-specs` — pre-implementation dev specs (written by `dev-spec-first-draft`; architecture,
  component breakdown, interfaces).

All three categories are shaped the same way:

| Field | Meaning |
|---|---|
| `location` | Where files in this category live (repo-root-relative, or `~`-relative) |
| `name-format` | Filename template, e.g. `<slug>.md` |
| `search` | Shell command that lists the files in this category |

`architecture.search` lists every doc in the category — run it as-is. `specs.search` and
`dev-specs.search` each find the document covering one work item, so they contain a
`<work-item-id>` placeholder — substitute the work-item-id into it before running.

A project that doesn't distinguish these categories can point them at the same `location`/`search`.

### `validation` — list of shell command strings, or `null`

A list of shell command strings, run in order from the repo root by the `validating` step of
the `implement` pipeline (via `run_validation.py`). Each command runs through a shell, so
operators like `&&`/`|` and environment variable expansion work same as they would in a
terminal. Execution stops at the first failing command.

**If `validation` is `null`, absent, or an empty list, this project has no validation
configured — the `implement` pipeline skips the validation step outright** (treated as an
immediate pass, same as the `work-tracking: null` convention above). This is the expected
configuration for a repo you don't own and that has no build/test script of its own: set

```yaml
validation:
```

(equivalently `validation: null`) in that repo's `.dev-team/config.yaml` (or
`.dev-team/config.local.yaml` if you don't want to commit the override). A project with a
single wrapper script:

```yaml
validation:
  - scripts/validate.sh
```

or with multiple discrete steps, run in order:

```yaml
validation:
  - npm run build
  - npm test
```

### `testing.test-file-patterns` — list of glob patterns

Glob patterns (matched against a file's basename) that identify a test file, used by the TDD
trio driver to keep `tdd-tester` scoped to test files and `tdd-implementer` scoped to production
files. Defaults to Python's `test_*.py` / `*_test.py` convention; override for a project using a
different language or naming convention, e.g.:

```yaml
testing:
  test-file-patterns:
    - "*.test.ts"
    - "*.spec.ts"
```

### `attribution.message` — string, or `null`

The wording used for the "Written by `<name>`" line that message-producing skills append to
commit messages, PR descriptions, PR/review comments, and work-item descriptions/comments — see
the `message-attribution` skill for the exact formatting rule and the list of channels it covers.
**If `attribution.message` is `null` or absent (the shipped default), no attribution line is
added anywhere.** Set an explicit value to opt in:

```yaml
attribution:
  message: Written by <name>
```

The configured string is used verbatim as `<name>` in `Written by <name>` — there is no
separate built-in default name to fall back to.

### `troubleshooter.can-fix` / `troubleshooter.can-push-fix` — booleans

Two independent authorization gates read by `workflow-troubleshoot`, both defaulting `false`
(the shipped default ships a blank `troubleshooter:` key — neither flag set). Issue searching
and filing is unconditional either way; these gates only affect whether the troubleshooter
attempts a root-cause code fix.

- **`can-fix`** — authorizes writing a root-cause fix and committing it on a branch in the
  plugin checkout `workflow-troubleshoot` resolves via `<skill-dir>`, then merging that branch
  directly into whatever is checked out there. No push, no PR.
- **`can-push-fix`** — has no effect unless `can-fix` is also set. Additionally authorizes
  pushing the fix branch and opening a draft PR via `gh stack`, instead of a local merge.

Set only in machine-tier config (`.dev-team/config.local.yaml`), never project-tier, since
authorization to make and push automated code changes is a personal, not project-wide,
decision:

```yaml
troubleshooter:
  can-fix: true
  can-push-fix: true
```

### `git-repo`

`user-alias` — substituted for `<user-alias>` in the `working-branches.*` templates below.
Defaults to `claude`; overridable per project or per machine (e.g. a human working in another
team's repo under their own alias, via `.dev-team/config.local.yaml`).

`working-branches.task` / `.feature` — branch name templates. The calling skill performs the
substitution; this skill only returns the raw template.

| Placeholder | Meaning |
|---|---|
| `<user-alias>` | From `git-repo.user-alias` |
| `<task-work-item-id>` | task-work-item ID, supplied by the calling skill |
| `<feature-work-item-id>` | feature-work-item ID, supplied by the calling skill |
| `<slug>` | Short kebab-case description, supplied by the calling skill |

### `instructions` — map of event name → ordered map of label → instruction

Each key is either `before-<event>` or `after-<event>-<trigger>`/`after-<event>` (e.g.
`before-implement`, `after-signoff-approved`), and its value is an ordered map of
`label: instruction` pairs — a short, stable label and a plain-language instruction describing
what to do at that point in the pipeline. Setting a label's value to `""` or `null` at a more
specific tier (e.g. `.dev-team/config.local.yaml`) disables just that one inherited entry; every
other label already present in that event's map is left untouched. Labels themselves are never
interpreted — they exist only so a more specific tier has something stable to key an override
against.

The `<trigger>` in an `after-<event>-<trigger>` key is the pipeline step's own actual trigger
string (e.g. `clean`/`build_failed` for `validate`, `approved`/`changes_requested` for
`signoff`/`review`) — see `update-project-configuration/SKILL.md`'s `instructions` section for
the full table of triggers per event. The deeper mechanics — the ordering guarantee across
tiers, resolution of which key(s) apply for a given event/phase, and merging the trigger-specific
map ahead of the unconditional `after-<event>` map — are owned by `dev_team.py` itself; only the
per-instruction dispatch (matching a label's plain-language instruction to the real tool call
that performs it) belongs to `run-hook-instructions`, the skill that follows an already-resolved
map. See both skills' own docs for their respective halves.
