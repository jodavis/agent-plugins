#!/usr/bin/env bash
set -euo pipefail

# The named volume mounts as root:root on first creation; hand it to vscode.
sudo chown -R vscode:vscode /home/vscode/.claude

# Claude Code CLI, pytest, and other shared tooling are baked into the image now.
seed-settings.sh
clone-agent-plugins.sh
