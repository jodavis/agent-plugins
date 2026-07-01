---
name: developer-standards
user-invocable: false
description: >
  Use when planning new code, writing code, or reviewing code.
  Loads project code guidelines and quality gates from CONTRIBUTING.md and CLAUDE.md.
---

## Steps

### 1 — Read code guidelines

Check the repo root for documentation files that define coding standards: naming conventions, file structure, logging, test conventions, quality gates, and operational requirements.

Read every file that exists from this list:

- `README.md`
- `CONTRIBUTING.md`
- `DEVELOPMENT.md`
- `STYLE.md` / `STYLEGUIDE.md`
- `HACKING.md`
- `CLAUDE.md`
- `AGENTS.md`
- `.github/CONTRIBUTING.md`
- `.github/copilot-instructions.md`
- `.cursorrules`

### 2 — Apply .editorconfig

Check for `.editorconfig` in the repo root. If present, read it and treat it as the authoritative code style specification. Follow every rule exactly — indentation, tab width, line endings, charset, trailing whitespace, final newlines, and any file-type overrides. No exceptions.

Apply all standards to every file you write or review.
