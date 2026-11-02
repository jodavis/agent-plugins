---
name: skill-checklist-review
user-invocable: false
description: >
  Use when asked to review, audit, score, or sanity-check a skill (a SKILL.md and its supporting
  files) against best practices — not when writing or revising one. Runs a deterministic
  structure check, then a judgment pass against references/checklist.md, and reports findings.
---

`<skill-dir>` below is this skill's own base directory — the "Base directory for this skill" path
shown when invoked — resolve it to that literal path.

Evaluates **one target skill directory** (passed in as an argument, e.g. `<target-dir>` below)
against `references/checklist.md`. Read that checklist in full before step 2 — it defines every
check this skill runs and is the only place their exact wording lives.

## Steps

### 1 — Run the structural check

```bash
python3 "<skill-dir>/scripts/check_skill_structure.py" "<target-dir>"
```

This covers every Group A item in the checklist. Relay its findings as-is — don't re-derive them
by re-reading the files; the script is authoritative for everything it checks. If it exits
non-zero, at least one finding is `error` severity.

### 2 — Read the target skill in full

Read `<target-dir>/SKILL.md` and every file it links to (which, per Group A, should be every file
under `references/` and `scripts/` — the script already flagged any that weren't). If the target
is itself large or references a lot of material, read all of it anyway: a judgment pass that
skips content isn't a judgment pass.

### 3 — Run the judgment pass

Work through `references/checklist.md` Group B, item by item. For each: quote the passage (or
note its absence), state whether it holds, and if not, the fix. Do not skip an item because it
"seems fine" without pointing at the specific text that makes it fine.

For Group B item 14 (trigger check), actually write out the sample phrasings and compare them
against the description's wording before concluding — don't just assert it would trigger.

**Gotchas in the structural check's findings:** `check_skill_structure.py` deliberately only
treats `references/...`, `scripts/...`, `assets/...` paths, and bare `<name>/SKILL.md` cross-skill
links as "local" — anything else (`~/...`, `.dev-team/config.yaml`-style runtime paths, or a
deeper path to another tool's own SKILL.md file, e.g. an installed plugin's) is intentionally not
checked for existence, because those were confirmed false positives (runtime config that
legitimately doesn't exist yet, or another tool's bundled skill outside this repo) when this
checker was run against every skill in this plugin.
An unresolved `<name>/SKILL.md` link is reported as `warn`, not `error`, for the same reason — it
might be a deliberate external reference. Don't "fix" the checker to flag these again without
re-confirming they're not still false positives.

**Gotcha — case-insensitive mounts can alias one directory under two names at once:** on a
case-insensitive-but-case-preserving filesystem (e.g. a macOS-host `virtiofs` bind mount, common
in this kind of container), confirmed empirically in this plugin: a single `iterdir()` call on
`skills/` returned both `work-with-github-issues` and `work-with-GitHub-issues` for the *same
inode*, apparently because the directory had been looked up with inconsistent casing earlier in
the session. "Find the one true on-disk name and string-compare against it" doesn't work against
that — which alias a plain listing returns first is non-deterministic. The checker compares by
inode instead (`_frontmatter_name_matches_dir()`): a `name-mismatch` only fires when no
case-insensitive match among the parent's entries shares `skill_dir`'s inode, which is immune to
however many aliases are floating around. If a `name-mismatch` still looks wrong, run
`stat -c '%i %n' <both-casings>` to check for exactly this before trusting the finding.

**Gotcha — a `missing-description` finding is real, but "delete the description" is the wrong
fix.** This plugin's commit `7fc2e20` (#279/#280) deleted `description:` from 73 internal-only
skills on the theory that a skill dispatched purely by name doesn't need one, and a missing
field costs nothing. Both halves of that theory are false here: a skill with no `description:`
gets one generated from its body, which can be as long as the skill itself and can read as a
match for requests the skill was never meant to handle — the opposite of "never auto-triggers."
When this finding is correct (the skill really is internal-only, dispatched by explicit name),
the fix is Group B item 2's short, deliberately inert line — `description: Only use when
instructed.` — never a bare deletion.

### 4 — Report

Produce one report, organized as:

- **Verdict** — one line: ready, or needs changes.
- **Errors** — any `error`-severity Group A finding. These block "ready."
- **Warnings / info** — remaining Group A findings, each with the checklist item it maps to.
- **Judgment findings** — every Group B item, in order, with its verdict and evidence. Include
  passing items too, briefly — a silent checklist item isn't a verified one.

Every finding cites its evidence — a quoted passage, a file:line, or a named absence. No finding
rests on a vibe.
