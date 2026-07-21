---
description: Initialize or update a .dev-team/config.yaml file (user-level, project-level, or a per-user local override).
argument-hint: [for user | for this project | for user in this project] [<setting to change>]
---

## Request

$ARGUMENTS

## Steps

### 1 — Parse location and target setting

Parse `$ARGUMENTS` for two independent, optional pieces of information:

- **Location phrase** — which config tier the user means:
  - "for user", "globally", "user-level", "on this machine" → `user`
  - "for this project", "for the project", "committed" → `project`
  - "for user in project", "just for me in this project", "locally", "locally here" → `user-in-project`
  - If no location phrase is present, leave it **unresolved** — do not default to `project`. The skill
    will ask.
- **Setting phrase** — free text naming what to change (e.g. "a work item source", "a work tracking
  source", "the validation script"). Pass it through verbatim; do not try to normalize it yourself.
  If nothing beyond a location phrase (or nothing at all) was given, there is no setting phrase.

Also note whether the user explicitly asked for a full walkthrough/initialization (e.g. "initialize",
"set it up", "full setup", "walk me through everything") — pass this along too.

### 2 — Run the configuration skill

Invoke the `update-project-configuration` skill, passing along:
- The parsed location (`user` / `project` / `user-in-project` / `unspecified`)
- The parsed setting phrase (verbatim, or `unspecified`)
- Whether a full walkthrough was explicitly requested
- The original `$ARGUMENTS`, so the skill can re-interpret anything this parse missed
