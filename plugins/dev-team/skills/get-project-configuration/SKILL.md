---
name: get-project-configuration
user-invocable: false
description: Only use when instructed.
---

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

See `references/config-schema.md` for the meaning of each field — `null` semantics,
path-like value resolution, and one subsection per top-level config key
(`developer-standards`, `work-tracking`, `documentation`, `validation`,
`testing.test-file-patterns`, `attribution.message`, `troubleshooter.*`, `git-repo`,
`instructions`). Only the field(s) relevant to what you're doing need reading, not the whole
file.
