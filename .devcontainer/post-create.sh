#!/usr/bin/env bash
set -euo pipefail

# The named volumes mount as root:root on first creation; hand them to vscode.
sudo chown -R vscode:vscode /home/vscode/.claude
sudo chown -R vscode:vscode /workspaces/agent-plugins

# Claude Code CLI, pytest, and other shared tooling are baked into the image now.
seed-settings.sh
clone-agent-plugins.sh
