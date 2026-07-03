#!/usr/bin/env bash
# get-todo-log-path.sh — Derive and create the dev-team todo log path.
#
# Usage: get-todo-log-path.sh <context_file> <work-item-id>
#
# Prints the todo log path, creating its parent directory and the (empty) file
# if they do not already exist.

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $(basename "$0") <context_file> <work-item-id>" >&2
    exit 1
fi
context_file="$1"
work_item_id="$2"

todo_log="$(dirname "$context_file")/logs/${work_item_id}-todo.log"
mkdir -p "$(dirname "$todo_log")"
touch "$todo_log"

echo "$todo_log"
