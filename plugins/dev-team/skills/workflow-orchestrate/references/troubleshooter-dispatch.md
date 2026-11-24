## Running the troubleshooter agent

When a problem occurs with the workflow, don't try to fix it. Spawn the troubleshooter agent to investigate:

```
Agent(
  subagent_type="dev-team:troubleshooter",
  prompt="""Invoke the `dev-team:workflow-troubleshoot` skill with arguments:
--context-file <context_file>
--problem "<problem_description>"
"""
)
```

Handle the outcome (a JSON object with `action` field):
- `"continue"` → continue the loop (the troubleshooter has edited the context file)
- `"terminate"` → report the reason to the user and stop
- `"needs_user_input"` →
  1. Ask the user the troubleshooter's question
  2. Write the user's answer to the `troubleshooter_input` frontmatter key in the
     context file by passing the answer via stdin:
     ```bash
     python3 -c "
     from pathlib import Path; import re, sys
     path = Path('<context_file>')
     answer = sys.stdin.read().strip()
     text = path.read_text(encoding='utf-8')
     text = re.sub(r'troubleshooter_input:.*', lambda m: f'troubleshooter_input: {answer}', text)
     path.write_text(text, encoding='utf-8')
     " <<'ANSWER_HEREDOC'
     <user_answer>
     ANSWER_HEREDOC
     ```
  3. Call the troubleshooter again with the user's input
