#!/usr/bin/env bash
set -euo pipefail

# The named volume mounts as root:root on first creation; hand it to vscode.
sudo chown -R vscode:vscode /home/vscode/.claude

# Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Test dependencies (CONTRIBUTING.md: pytest, pytest-asyncio, pytest-mock)
pip3 install --user pytest pytest-asyncio pytest-mock
