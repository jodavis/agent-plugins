# Full walkthrough sections

### work-tracking

Detect a hint first:

```bash
git remote -v
git log --oneline -50 | grep -oE '[A-Z][A-Z0-9]+-[0-9]+' | sort -u | head -5
```

A GitHub remote suggests a `github` block; recurring `XXXX-123`-style tokens in log messages suggest a
`jira` block with that pattern as `issue-key-pattern`. Ask which provider(s) apply (can be both, or
`null`/empty for none). For each provider selected, ask/confirm:

- `issue-key-pattern` — regex identifying that provider's IDs
- `recognize-patterns` — list of alternate phrasings a user might type (e.g. `Task \d+`, `#\d+`)
- `task-work-item` block: `type` (the tracker's real name, e.g. `Task`/`Issue`), plus
  `replace-description-when` / `update-description-when`
- `feature-work-item` block (Jira only, typically): same shape, `type` e.g. `Epic`
- Any free-form item-type blocks the project wants (e.g. `bug-item`)

If the user says there's no tracker, write `work-tracking:` with an empty/null value — don't omit the
key silently, since `get-project-configuration` treats an explicit `null` differently from "inherit
from a lower tier."

### documentation

Detect a hint first:

```bash
ls docs/ specs/ documentation/ 2>/dev/null
find . -maxdepth 3 -iname "*_spec_*.md" -o -iname "*_doc_*.md" 2>/dev/null | head -5
```

Ask: doc format (default `Markdown`); then for `architecture` (post-implementation docs) and `specs`
(pre-implementation docs) each: `location`, `name-format`, `search` command. If the project doesn't
distinguish the two, point both at the same location/search.

### developer-standards

The shipped default already lists the common candidate filenames (README, CONTRIBUTING, CLAUDE.md,
etc.) as soft entries — those don't need restating unless the project deviates. Ask only: "Any other
files that document conventions or how to work in this repo?" and add filename → description entries
for anything named. Use the `"If this file exists, read it — ..."` prefix convention (see
`get-project-configuration`'s SOFT_FILE_PREFIX handling) if the file's presence is uncertain.

### validation

Detect a hint first:

```bash
ls scripts/validate* 2>/dev/null
grep -l '"test"\|"build"' package.json 2>/dev/null
ls Makefile pyproject.toml tox.ini 2>/dev/null
```

Ask for the list of shell commands that build/test this project (run in order from the repo
root; stops at the first failing command). If there isn't one, set `validation: null` explicitly
— this is a deliberate, expected value (see `get-project-configuration`'s documented
no-validation convention), not an omission.

### testing

Detect a hint first:

```bash
find . -maxdepth 3 -iname "test_*.py" -o -iname "*_test.py" -o -iname "*.test.ts" -o -iname "*.spec.ts" -o -iname "*Tests.cs" -o -iname "*Test.cs" 2>/dev/null | head -10
```

Ask for the glob pattern(s) (matched against basename) that identify a test file in this project.

### git-repo

Ask/confirm:
- `user-alias` — defaults to `claude`; ask if this user works under a different alias in this repo
- `working-branches.task` / `.feature` — branch name templates (placeholders:
  `<user-alias>`, `<task-work-item-id>`, `<feature-work-item-id>`, `<slug>`)

### instructions

Detect a hint first: run `merge_config.py` (already loaded in Step 2, or re-run here) and read the
merged `instructions` map. Each key is either `before-<event>` (runs before the step's real
dispatch, unconditionally), `after-<event>` (runs after, regardless of outcome), or
`after-<event>-<trigger>` (runs after, only when the step's own trigger matches `<trigger>`
exactly — e.g. `after-validate-clean` vs. `after-validate-build_failed`, `after-signoff-approved`
vs. `after-signoff-changes_requested`). Each key holds an ordered `label: instruction` map.
`dev_team.py` owns resolving which keys apply and in what order (trigger-specific entries before
the unconditional `after-<event>` entries); `run-hook-instructions` owns dispatching an
already-resolved map to the real tool call each instruction describes — this subsection doesn't
repeat either's mechanics.

Available `<trigger>` values per event (a step whose trigger isn't listed here — `research`,
`create-pr`, `plan`, `fix` — only ever has one outcome shape, so only the unconditional
`after-<event>` key applies to it):

| Event | Triggers |
|---|---|
| `debug` | `debug_done`, `reproduction_failed` |
| `implement` | `impl_done` |
| `validate` | `clean`, `build_failed` |
| `review` | `approved`, `changes_requested` |
| `signoff` | `approved`, `changes_requested` |

Present the current merged instructions, leading with the events that ship non-empty defaults
(`after-validate-clean`, `before-create-pr`) and offering the remaining events on request rather
than listing all of them unconditionally.

For each event the user wants to change, ask which action applies:
- **Add** a new labeled entry — ask for a label (an opaque key, only used to override this one
  entry at a more specific tier — never interpreted by the hook mechanism) and the instruction
  text in plain language (e.g. "Push git changes to remote").
- **Edit** an existing labeled entry — show its current instruction text and ask for the
  replacement.
- **Disable** an existing labeled entry — write `label: ""` at the tier being edited. This
  overrides just that one inherited label, leaving its siblings (and every other event's entries)
  untouched. If the user has no push/PR rights on this repo (e.g. contributing to another team's
  repo), disable the relevant labeled entries this way — there is no block-level `enabled: false`
  under `instructions:`.

Then ask specifically who should be assigned as PR/work-item reviewer once signoff approves the
work: write the answer into `after-signoff-approved`'s `request-review` label (a GitHub username,
for requesting review on the PR) and `assign-work-item` label (an email or account identifier, for
assigning the tracked work item) — ask for both forms if the user's single answer doesn't
unambiguously give both. (`after-signoff-approved` is this config schema's key for the pipeline's
sign-off step — `SignoffStep`'s own `EVENT_NAME` is `signoff`, and its `"approved"` trigger is
what a clean sign-off actually returns.)

### attribution

Ask: should messages written on the user's behalf (commit messages, PR descriptions, PR/review
comments, work-item comments and descriptions) carry an attribution line? If yes, ask
for the exact wording (e.g. "Written by <name>") and set
`attribution.message` to it verbatim — that string is used as-is, with no separate built-in
default. If no, leave `attribution.message` unset/`null`; this is the shipped default and needs
no explicit write.

