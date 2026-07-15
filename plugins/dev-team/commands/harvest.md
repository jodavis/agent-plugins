---
description: >
  Use when turning a validated spec and/or exemplar repos into a reusable playbook.
argument-hint: <spec-path | none> [--exemplar <repo-path>]... [--template-output <path>] --out <playbook-directory> [--name <playbook-name>]
---

## Request

$ARGUMENTS

## Steps

### 1 — Parse the harvest arguments

Parse `$ARGUMENTS` for: the spec path (or `none`, for a purely exemplar-driven harvest), zero
or more `--exemplar <repo-path>` flags, an optional `--template-output <path>`, the required
`--out <playbook-directory>`, and an optional `--name <playbook-name>`. These may also be given
conversationally rather than as flags.

If `--out` is missing, tell the user:

> Please provide an output directory for the playbook (e.g. `--out path/to/playbooks/my-playbook`).

Then stop.

### 2 — Run the harvest

Invoke the `harvest-playbook` skill with the parsed arguments.
