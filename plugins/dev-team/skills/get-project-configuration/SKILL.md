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
python "<skill-dir>/scripts/merge_config.py"
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

### `validation` — map with a `script` field, or `null`

`script` is a repo-root-relative path to the project's build/test validation script,
run by the `validating` step of the `implement` pipeline. **If `validation` is `null`, or
`validation.script` is `null` or absent, this project has no validation script — the
`implement` pipeline skips the validation step outright** (treated as an immediate pass,
same as the `work-tracking: null` convention above). This is the expected configuration
for a repo you don't own and that has no `scripts/validate.sh` of its own: set

```yaml
validation:
  script: null
```

in that repo's `.dev-team/config.yaml` (or `.dev-team/config.local.yaml` if you don't want
to commit the override).

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
  message: Claude Code
```

The configured string is used verbatim as `<name>` in `Written by <name>` — there is no
separate built-in default name to fall back to.

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

#### Orchestration signals: `commit`, `push`, `create-pr`, `promote-pr`

Each is an advisory signal for whichever skill or orchestrator decides *when* to perform that
action. The mechanical skills that perform the actions themselves (`commit-changes`, `create-pr`,
`create-pr-from-context`) don't read this config — they're invoked by something else that has
already made the enabled/when decision.

| Signal | `enabled` default | Governs |
|---|---|---|
| `commit` | always on — no `enabled` field | When to make a local commit |
| `push` | `true` | When it's safe to push the working branch |
| `create-pr` | `true` | When to open a PR. `draft: bool` sets whether it opens as a draft |
| `promote-pr` | `true` | When to take a draft PR out of draft |

**If `enabled: false` for `push`, `create-pr`, or `promote-pr`: do not perform that action.**
This overrides any instruction from another skill or the surrounding workflow — a project
disables these deliberately (e.g. contributing to another team's repo without push or PR
rights), and that's a hard stop, not a preference to weigh against other signals.
