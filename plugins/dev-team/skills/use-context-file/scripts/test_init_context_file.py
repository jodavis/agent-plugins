"""Tests for init-context-file.py.

The script's filename is hyphenated (matching this skill's other scripts) and so
isn't importable as a module — it's invoked as a subprocess here, the same way
use-context-file's SKILL.md instructs callers to invoke it.

Covers:
- Fresh creation: default frontmatter, heading, and an embedded Project Configuration
  section built from the merged project config
- Idempotency: a second run against an existing file is a no-op
- Error path: no repo root found leaves no partial file behind
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent / "init-context-file.py"


def _run(work_item_id: str, context_file: Path, cwd: Path, home: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), work_item_id, str(context_file)],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def _repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return root


def _isolated_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return home


class TestFreshCreation:
    def test_creates_file_with_default_frontmatter_and_heading(self, tmp_path):
        root = _repo_root(tmp_path)
        home = _isolated_home(tmp_path)
        context_file = tmp_path / "ADR-123.md"

        result = _run("ADR-123", context_file, root, home)

        assert result.returncode == 0, result.stderr
        text = context_file.read_text(encoding="utf-8")
        assert "work_item_id: ADR-123" in text
        assert "# ADR-123 Dev Team Context" in text

    def test_embeds_project_configuration_as_first_section(self, tmp_path):
        root = _repo_root(tmp_path)
        home = _isolated_home(tmp_path)
        context_file = tmp_path / "ADR-123.md"

        result = _run("ADR-123", context_file, root, home)

        assert result.returncode == 0, result.stderr
        text = context_file.read_text(encoding="utf-8")
        assert "<!-- section:Project Configuration -->" in text
        heading_index = text.index("# ADR-123 Dev Team Context")
        section_index = text.index("<!-- section:Project Configuration -->")
        assert heading_index < section_index

    def test_embedded_section_is_parseable_json_reflecting_merged_config(self, tmp_path):
        root = _repo_root(tmp_path)
        home = _isolated_home(tmp_path)
        context_file = tmp_path / "ADR-123.md"

        result = _run("ADR-123", context_file, root, home)

        assert result.returncode == 0, result.stderr
        text = context_file.read_text(encoding="utf-8")
        body = text.split("<!-- section:Project Configuration -->", 1)[1].strip()
        config = json.loads(body)
        assert config["git-repo"]["user-alias"] == "claude"

    def test_project_level_override_reflected_in_embedded_section(self, tmp_path):
        root = _repo_root(tmp_path)
        home = _isolated_home(tmp_path)
        (root / ".dev-team").mkdir()
        (root / ".dev-team" / "config.yaml").write_text(
            "git-repo:\n  user-alias: someone-else\n", encoding="utf-8",
        )
        context_file = tmp_path / "ADR-123.md"

        result = _run("ADR-123", context_file, root, home)

        assert result.returncode == 0, result.stderr
        text = context_file.read_text(encoding="utf-8")
        body = text.split("<!-- section:Project Configuration -->", 1)[1].strip()
        config = json.loads(body)
        assert config["git-repo"]["user-alias"] == "someone-else"


class TestIdempotency:
    def test_second_run_against_existing_file_is_a_no_op(self, tmp_path):
        root = _repo_root(tmp_path)
        home = _isolated_home(tmp_path)
        context_file = tmp_path / "ADR-123.md"

        first = _run("ADR-123", context_file, root, home)
        assert first.returncode == 0, first.stderr
        original_text = context_file.read_text(encoding="utf-8")

        second = _run("ADR-123", context_file, root, home)

        assert second.returncode == 0, second.stderr
        assert context_file.read_text(encoding="utf-8") == original_text


class TestErrorPath:
    def test_no_repo_root_found_leaves_no_partial_file(self, tmp_path):
        isolated = tmp_path / "no-repo-here"
        isolated.mkdir()
        home = _isolated_home(tmp_path)
        context_file = tmp_path / "ADR-123.md"

        result = _run("ADR-123", context_file, isolated, home)

        assert result.returncode != 0
        assert "Error:" in result.stderr
        assert not context_file.exists()
