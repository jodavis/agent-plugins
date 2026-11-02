## Running the troubleshooter agent

When step 2d notices something broken for a specific task_id that isn't covered by the staleness
check, don't try to fix it yourself. Spawn the troubleshooter agent to investigate, against that
task_id's own context file — resolved the same way step 2c/`use-context-file` already resolves it
for that task, never `concurrent_schedule.py`'s own scheduler state file (a different, plain-JSON
format, incompatible with `workflow-troubleshoot`'s YAML-frontmatter context-file convention):

```
Agent(
  subagent_type="dev-team:troubleshooter",
  prompt="""Invoke the `dev-team:workflow-troubleshoot` skill with arguments:
--context-file <task's own context_file>
--problem "<problem_description>"
"""
)
```

Handle the outcome (a JSON object with `action` field), identically to how
`workflow-orchestrate`'s own "Running the troubleshooter agent" section handles it:
- `"continue"` → resume the poll loop at step 2a (the troubleshooter has edited that task's
  context file)
- `"terminate"` → report the reason to the user and stop
- `"needs_user_input"` →
  1. Ask the user the troubleshooter's question
  2. Write the user's answer to the `troubleshooter_input` frontmatter key in that task's context
     file by passing the answer via stdin:
     ```bash
     python3 -c "
     from pathlib import Path; import re, sys
     path = Path('<task's own context_file>')
     answer = sys.stdin.read().strip()
     text = path.read_text(encoding='utf-8')
     text = re.sub(r'troubleshooter_input:.*', lambda m: f'troubleshooter_input: {answer}', text)
     path.write_text(text, encoding='utf-8')
     " <<'ANSWER_HEREDOC'
     <user_answer>
     ANSWER_HEREDOC
     ```
  3. Call the troubleshooter again with the user's input

This dispatch is scoped to anomalies tied to one task_id. A scheduler-level anomaly — not tied to
any task (e.g. `concurrent_schedule.py` itself exiting non-zero) — is out of scope for this
section; step 2a's existing stop-and-report handling covers that case unchanged.

