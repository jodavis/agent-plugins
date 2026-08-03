---
name: run-python-script
user-invocable: false
description: >
  Shared skill that centralizes the `python3` availability check and script invocation. Verifies
  `python3` is present (skipping the check if already verified earlier in this session) and stops
  with a clear, stop-and-tell-the-user failure if missing, then runs a given Python script (with
  its arguments) via `python3`. Every other skill that invokes a Python script should delegate to
  this skill instead of inlining its own `python3 <script>` call, so there is exactly one place
  to change the interpreter requirement later.
argument-hint: --script <path> [--python-flags "<flags>"] [--args "<arg1> <arg2> ..."] [--stdin "<text>"] [--timeout <ms>]
---

Use this skill when:
- You are about to run a Python script via `python3` as part of a skill's own steps

Do NOT use this skill when:
- The command you need to run is a pre-built shell string handed to you by a caller, not a
  literal `python3 <script>` invocation you are constructing yourself — e.g. `workflow-script`'s
  `--command` argument. That contract stays exactly as-is; see "Carve-outs" below.

## Arguments

- `--script` — the Python script to run, as a path already resolved by the caller (e.g.
  `"<skill-dir>/scripts/foo.py"`) — this skill does not resolve `<skill-dir>` itself
- `--python-flags` — (optional) flags for the `python3` interpreter itself, placed before the
  script path (e.g. `-u` for unbuffered stdout) — distinct from `--args`, which is placed after
  the script path and passed to the script's own argv
- `--args` — (optional) the script's own arguments, exactly as they'd appear on the command line
- `--stdin` — (optional) text to pipe to the script's stdin (e.g. via a heredoc), for a script
  that reads piped input rather than argv (e.g. `tdd_cycle.py`'s component prompt)
- `--timeout` — (optional) an explicit `Bash` tool timeout in milliseconds, for a script the
  caller knows blocks internally past the default timeout (e.g. a polling script with its own
  multi-minute internal wait budget). Omit to use the `Bash` tool's own default.

## Steps

### 1 — Verify `python3` is available (skip if already verified this session)

If you have already verified `python3` is present earlier in this same session — whether via an
earlier call to this skill, or an earlier explicit preflight check — skip straight to step 2.
There is no session-state file for this; it relies on the same in-context recall convention every
prior preflight step in this pipeline already used ("before running step 1 for the first time
this session").

Otherwise, confirm the interpreter is present:

```bash
command -v python3
```

If this reports nothing (a non-zero exit), stop immediately and report to the user that `python3`
is required but was not found on this system, rather than proceeding and failing on the script
invocation itself with a less obvious "command not found" error. Do not attempt to install
`python3`, fall back to a bare `python` command, or probe for any other interpreter — this
project standardizes fully on `python3`, no fallback-detection chain.

Otherwise, remember for the rest of this session that `python3` has been verified, so this step
is a no-op on every later call to this skill (or any other step in this session that would
otherwise re-check it).

### 2 — Run the script

```bash
python3 <python-flags> "<script>" <args>
```

Omit `<python-flags>` entirely when `--python-flags` was not given — do not insert an empty
argument in its place. If `--stdin` was given, pipe it in (e.g. via a heredoc) instead of running
the bare command. If `--timeout` was given, pass it as the `Bash` tool's own `timeout` parameter
for this call.

Capture stdout/stderr per the calling skill's own contract for this specific script — this skill
only ensures the interpreter is present and executes the script; it does not interpret, parse, or
reformat the script's output itself. The calling skill's own instructions for what to do with the
output (parse JSON, check exit code, treat a non-JSON last line a certain way, etc.) are unchanged
by routing the invocation through this skill.

## Carve-outs (not migrated to this skill)

- **`workflow-script`'s `--command` argument.** Its `<command>` is a pre-built shell string handed
  in by the caller (sometimes literally `python3 ...`, sometimes built by `dev_team.py` using
  `sys.executable`) — `workflow-script` runs whatever string it's given via `Bash`, it never
  constructs a `python3 <script>` invocation itself the way every other skill migrated to this
  skill does. No functional change; this is documented here as the intentional reason it stays
  out of scope.
- **Inline `python3 -c "<code>"` blocks** (`workflow-orchestrate/SKILL.md`'s
  `troubleshooter_input` write, `monitor-pr/SKILL.md`'s rebase-mechanic invocation). These run
  inline code, not a script file at a path — outside this skill's `--script <path>` shape. Each
  stays as a direct inline `python3 -c` call. Since both live in skills whose own earlier steps
  already call this skill first in the same session (`workflow-orchestrate`'s step 1;
  `monitor-pr`'s step 4a via the sibling `watch_pr_poll.py` call), `python3`'s availability is
  already established in-session by the time either inline block runs — no separate preflight is
  needed at these two call sites.
- **`dev_team.py`'s two generated command strings** (`_resolve_validation_script()`,
  `BuildValidationStep.get_actions()`) — these already use `sys.executable`, not a literal
  `python3` invocation, because that code path is real Python building a command string for a
  later shell invocation, not agent-facing skill prose constructing a `python3 <script>` call
  itself. This skill only wraps the latter; no change is needed here.
