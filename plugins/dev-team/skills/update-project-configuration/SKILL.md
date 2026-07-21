---
name: update-project-configuration
user-invocable: false
description: >
  Use when initializing or changing settings in a .dev-team/config.yaml file (user-level, project-level,
  or a per-user local override) — either a full guided walkthrough or a single setting. Companion to
  get-project-configuration, which reads the merged result; this skill writes the tiers that feed it.
---

Use this skill when:
- The user wants to set up dev-team configuration for the first time (full initialization)
- The user wants to change one specific setting (e.g. "the work item source", "the validation script")
- The user isn't sure what's configurable and wants a menu of options

This skill only writes files. It never edits the shipped default
(`get-project-configuration/assets/default-config.yaml`) — that tier is read-only.

## The three writable tiers

| Location phrase | File | Committed? | Typical use |
|---|---|---|---|
| "for user" / "globally" / "on this machine" | `~/.dev-team/config.yaml` | N/A — not in any repo | Machine-wide defaults. Also the right place for project-shaped settings (work-tracking, documentation, etc.) on a repo the user doesn't want to add dev-team config *files* to — e.g. a work-for-hire repo. Don't treat this tier as "minor overrides only"; it deserves the same full walkthrough as the project tier. |
| "for this project" / "for the project" / "committed" | `<repo-root>/.dev-team/config.yaml` | Yes | Shared with the whole team working in this repo |
| "for user in project" / "just for me in this project" / "locally" | `<repo-root>/.dev-team/config.local.yaml` | No — gitignored | One person's override of the committed project config, without affecting teammates |

Precedence (lowest to highest): shipped default < user < project < user-in-project. See
`get-project-configuration`'s `merge_config.py` for the authoritative merge logic — this skill writes
the inputs to that merge, and should re-run it after writing (see "Verifying a write" below).

**Auto-detection always looks at the current repo, regardless of which tier is being written.** Even
when writing to the user-level file, the point is usually still "configure this for the repo I'm
sitting in, just without a file in that repo" — so detect from the current repo's state (`git remote`,
existing folders, etc.) the same way for every tier.

## Step 1 — Resolve the location

If the calling command already parsed a location, use it. Otherwise **ask directly** — never default
silently to `project`:

> Where should this apply?
> - For user (`~/.dev-team/config.yaml`) — applies on this machine, across repos
> - For this project (`<repo-root>/.dev-team/config.yaml`) — committed, shared with the team
> - Just for me, in this project (`<repo-root>/.dev-team/config.local.yaml`) — gitignored, personal override

Resolve `<repo-root>` the same way `merge_config.py` does: walk up from the current directory until a
`.git` or `.claude` directory is found.

## Step 2 — Resolve the action

- If a setting phrase was given (or is clear from conversation), go to **Step 3 — Single setting**.
- If the user explicitly asked for a full walkthrough/initialization, go to **Step 4 — Full walkthrough**.
- Otherwise, load the current merged config for context:

  ```bash
  python "<get-project-configuration-skill-dir>/scripts/merge_config.py" --repo-root "<repo-root>"
  ```

  `<get-project-configuration-skill-dir>` is that skill's own base directory — a sibling of this
  skill's directory (both live directly under `plugins/dev-team/skills/`). Resolve it to the literal
  path; it is not an environment variable.

  (This reads all tiers up to and including project/local; it doesn't tell you what's set in the
  *specific* file you're about to write, only the effective result. To know what a specific tier
  already has explicitly, read that file directly — a key absent from it is "not set at this tier",
  even if inherited from a lower tier.)

  Then present a menu:

  > What would you like to configure?
  > - **Not yet configured**: <list sections/fields still equal to the shipped default or null>
  > - Show everything (all six sections, including ones already set)
  > - Run the full guided walkthrough top-to-bottom

  Default the menu to the "not yet configured" list per the user's own framing — but always offer the
  other two as explicit options.

## Step 3 — Single setting

Match the user's free-text phrase against this table. If nothing matches with reasonable confidence,
ask the user to clarify rather than guessing — do not silently pick the closest row.

| User might say | Config path | Notes |
|---|---|---|
| "work item source", "work tracking source", "issue tracker", "ticket system" | `work-tracking` | Ask which provider(s): `jira`, `github`, both, or none. See Step 4 for the fields under each. |
| "developer standards", "coding conventions files", "style guide files" | `developer-standards` | Filename → description map |
| "documentation location", "docs folder", "where docs live" | `documentation.architecture` | |
| "spec location", "where specs live" | `documentation.specs` | |
| "doc format" | `documentation.format` | |
| "validation script", "build/test script", "how to validate" | `validation.script` | Set to `null` explicitly if the project has none |
| "test file naming", "test file pattern" | `testing.test-file-patterns` | List of glob patterns |
| "git user alias", "my alias" | `git-repo.user-alias` | |
| "branch naming", "working branch template" | `git-repo.working-branches` | `task` and `feature` templates |
| "commit/push/PR behavior", "when to push", "draft PRs", "auto-PR" | `git-repo.push` / `.create-pr` / `.promote-pr` | Each has `enabled` + `when`; `create-pr` also has `draft` |

Once the config path is resolved, ask only the question(s) for that field/section (reuse the relevant
sub-section under Step 4), then go to **Step 5 — Writing**.

## Step 4 — Full walkthrough

Walk through each section below in order. For each: run the detection command if one is given, present
the detected value as a suggested default, and let the user accept, override, or **skip** (leave that
field untouched at this tier). Skipping is always valid — don't force a value out of the user.

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

Ask for the repo-root-relative path to the build/test validation script. If there isn't one, set
`validation.script: null` explicitly — this is a deliberate, expected value (see
`get-project-configuration`'s documented no-validation convention), not an omission.

### testing

Detect a hint first:

```bash
find . -maxdepth 3 -iname "test_*.py" -o -iname "*_test.py" -o -iname "*.test.ts" -o -iname "*.spec.ts" 2>/dev/null | head -10
```

Ask for the glob pattern(s) (matched against basename) that identify a test file in this project.

### git-repo

Ask/confirm:
- `user-alias` — defaults to `claude`; ask if this user works under a different alias in this repo
- `working-branches.task` / `.feature` — branch name templates (placeholders:
  `<user-alias>`, `<task-work-item-id>`, `<feature-work-item-id>`, `<slug>`)
- `commit.when` — when to make a local commit
- `push.enabled` / `.when`
- `create-pr.enabled` / `.draft` / `.when`
- `promote-pr.enabled` / `.when`

If the user has no push/PR rights on this repo (e.g. contributing to another team's repo), set the
relevant `enabled: false` rather than leaving `when` vague.

## Step 5 — Writing the file

Edit the target YAML file as **text**, not as a parsed/re-serialized structure — there is no YAML
writer in this plugin, only `merge_config.py`'s reader, and hand-editing preserves comments and
existing formatting:

- **File doesn't exist yet**: create it (and the `.dev-team/` directory, if needed) containing only
  the sections/fields the user actually set — don't dump the full six-section schema with placeholder
  values. Follow the style of the existing example configs (see either the shipped
  `assets/default-config.yaml` or this repo's own `.dev-team/config.yaml` for indentation/quoting
  conventions).
- **File exists**: make targeted edits — replace just the changed scalar/block, add new keys at the
  right nesting level, and leave everything else (including comments) untouched.
- **Writing `config.local.yaml` for the first time**: check the target repo's `.gitignore` for a
  `.dev-team/config.local.yaml` (or `*.local.yaml`) entry; if absent, add one — this file must never be
  committed.

## Verifying a write

After writing, re-run `merge_config.py` against the same repo root and show the user the relevant part
of the merged result, confirming the change took effect as intended:

```bash
python "<get-project-configuration-skill-dir>/scripts/merge_config.py" --repo-root "<repo-root>"
```

If it exits non-zero (malformed YAML), report the exact error — the edit introduced a syntax problem
that must be fixed before the write can be considered done.
