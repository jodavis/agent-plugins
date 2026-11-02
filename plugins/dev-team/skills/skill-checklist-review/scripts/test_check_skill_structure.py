"""Tests for check_skill_structure.py — the deterministic Group-A checker behind the
`skill-checklist-review` skill.

Covers:
- parse_frontmatter(): plain keys, a folded `description: >` scalar, and a missing/malformed
  frontmatter block.
- check_frontmatter(): name/directory match and mismatch, missing name, missing description, a
  conspicuously long description, and a differently-cased `skill_dir` argument still resolving to
  the true on-disk name instead of a false mismatch (the case-insensitive-filesystem gotcha).
- check_references(): a dangling link from SKILL.md, an orphaned references/ file, a chained
  reference-to-reference link (and the dangling-link check applying inside that chain too).
- check_scripts_have_tests(): a script with a matching test_*.py, one with none, and test files
  themselves never being flagged.
- grep_historical(): a line matching a historical phrase, and a clean line producing nothing.
- check_skill_md_length(): a long body with no references/ dir flags info; the same long body
  with a references/ dir present does not; a short body never flags regardless.
- evaluate() end-to-end: a fully clean skill directory produces zero findings and a 0 exit code
  via main(); a broken one produces the expected error/warn/info mix and exit code 1.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "check_skill_structure.py"
sys.path.insert(0, str(Path(__file__).parent))

from check_skill_structure import (  # noqa: E402
    check_frontmatter,
    check_references,
    check_scripts_have_tests,
    check_skill_md_length,
    evaluate,
    grep_historical,
    parse_frontmatter,
    _frontmatter_name_matches_dir,
)


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class _FakeStat:
    def __init__(self, ino):
        self.st_ino = ino


class _FakeEntry:
    """Duck-types a Path dirent: .name and .stat().st_ino, nothing else."""

    def __init__(self, name, ino):
        self.name = name
        self._ino = ino

    def stat(self):
        return _FakeStat(self._ino)


class _FakeDir(_FakeEntry):
    """Duck-types a Path used as skill_dir: adds .parent.iterdir() over fixed siblings."""

    def __init__(self, name, ino, siblings):
        super().__init__(name, ino)
        self._siblings = siblings
        self.parent = self

    def iterdir(self):
        return iter(self._siblings)


class TestParseFrontmatter:
    def test_plain_keys(self):
        data, consumed = parse_frontmatter("---\nname: foo\nuser-invocable: false\n---\nbody\n")

        assert data == {"name": "foo", "user-invocable": "false"}
        assert consumed == 4

    def test_folded_description_scalar(self):
        text = "---\nname: foo\ndescription: >\n  Use when X.\n  Does Y.\n---\n"

        data, _ = parse_frontmatter(text)

        assert data["description"] == "Use when X. Does Y."

    def test_no_frontmatter_block_returns_empty(self):
        data, consumed = parse_frontmatter("no frontmatter here\n")

        assert data == {}
        assert consumed == 0

    def test_unterminated_frontmatter_returns_empty(self):
        data, consumed = parse_frontmatter("---\nname: foo\n")

        assert data == {}
        assert consumed == 0


class TestCheckFrontmatter:
    def test_name_matches_directory_passes(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()

        findings = check_frontmatter(skill_dir, {"name": "my-skill", "description": "Use when X."})

        assert findings == []

    def test_name_mismatch_is_error(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()

        findings = check_frontmatter(skill_dir, {"name": "other-name"})

        assert any(f["id"] == "name-mismatch" and f["severity"] == "error" for f in findings)

    def test_missing_name_is_error(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()

        findings = check_frontmatter(skill_dir, {})

        assert any(f["id"] == "missing-name" and f["severity"] == "error" for f in findings)

    def test_missing_description_is_warn(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()

        findings = check_frontmatter(skill_dir, {"name": "my-skill"})

        assert any(f["id"] == "missing-description" and f["severity"] == "warn" for f in findings)

    def test_long_description_is_info(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        long_description = " ".join(["word"] * 81)

        findings = check_frontmatter(skill_dir, {"name": "my-skill", "description": long_description})

        assert any(f["id"] == "long-description" and f["severity"] == "info" for f in findings)

    def test_inode_aliased_entries_are_not_a_mismatch(self):
        # Simulates the virtiofs bug confirmed empirically in this repo: a single directory
        # listing returned the SAME inode under two different-case names at once
        # ('work-with-github-issues' and 'work-with-GitHub-issues'). Not portably reproducible
        # on a real (likely case-sensitive) test filesystem, so this drives
        # _frontmatter_name_matches_dir directly with duck-typed stand-ins exposing only
        # .name/.stat().st_ino/.parent.iterdir() — matching by inode must hold regardless of
        # which case-variant entry a given run happens to list first.
        real = _FakeEntry("work-with-github-issues", ino=42)
        alias = _FakeEntry("work-with-GitHub-issues", ino=42)
        skill_dir = _FakeDir("work-with-GitHub-issues", ino=42, siblings=[real, alias])

        assert _frontmatter_name_matches_dir(skill_dir, "work-with-github-issues") is True

    def test_genuinely_different_inode_is_a_mismatch(self):
        other = _FakeEntry("some-other-skill", ino=99)
        skill_dir = _FakeDir("my-skill", ino=1, siblings=[other])

        assert _frontmatter_name_matches_dir(skill_dir, "some-other-skill") is False


class TestCheckReferences:
    def test_dangling_link_in_skill_md_is_error(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()

        findings = check_references(skill_dir, "See [docs](references/missing.md).\n")

        assert any(f["id"] == "dangling-link" and f["file"] == "SKILL.md" for f in findings)

    def test_linked_existing_reference_has_no_dangling_finding(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        _write(skill_dir / "references" / "checklist.md", "Nothing to see here.\n")

        findings = check_references(skill_dir, "See [docs](references/checklist.md).\n")

        assert findings == []

    def test_orphan_reference_file_is_warn(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        _write(skill_dir / "references" / "orphan.md", "Nobody links to me.\n")

        findings = check_references(skill_dir, "No links here.\n")

        assert any(
            f["id"] == "orphan-reference" and f["file"] == "references/orphan.md" for f in findings
        )

    def test_cross_skill_link_resolved_against_skills_root_is_not_dangling(self, tmp_path):
        skills_root = tmp_path / "skills"
        skill_dir = skills_root / "my-skill"
        skill_dir.mkdir(parents=True)
        _write(skills_root / "other-skill" / "SKILL.md", "---\nname: other-skill\n---\n")

        findings = check_references(skill_dir, "See `other-skill/SKILL.md` for detail.\n")

        assert not any(f["id"] == "dangling-link" for f in findings)

    def test_unresolved_cross_skill_link_is_warn_not_error(self, tmp_path):
        skills_root = tmp_path / "skills"
        skill_dir = skills_root / "my-skill"
        skill_dir.mkdir(parents=True)

        findings = check_references(skill_dir, "See `no-such-skill/SKILL.md` for detail.\n")

        assert any(f["id"] == "unresolved-cross-skill-link" and f["severity"] == "warn" for f in findings)
        assert not any(f["id"] == "dangling-link" for f in findings)

    def test_runtime_config_style_path_is_ignored(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()

        findings = check_references(
            skill_dir, "See this repo's own `.dev-team/config.yaml` and `~/.dev-team/config.yaml`.\n"
        )

        assert findings == []

    def test_reference_chain_is_warn_and_dangling_target_is_error(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        _write(
            skill_dir / "references" / "a.md",
            "See [more](references/missing-b.md) for detail.\n",
        )

        findings = check_references(skill_dir, "See [docs](references/a.md).\n")

        assert any(f["id"] == "reference-chain" and f["file"] == "references/a.md" for f in findings)
        assert any(f["id"] == "dangling-link" and f["file"] == "references/a.md" for f in findings)


class TestCheckScriptsHaveTests:
    def test_script_with_matching_test_file_passes(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        _write(scripts_dir / "do_thing.py", "")
        _write(scripts_dir / "test_do_thing.py", "")

        assert check_scripts_have_tests(scripts_dir) == []

    def test_script_without_test_file_is_warn(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        _write(scripts_dir / "do_thing.py", "")

        findings = check_scripts_have_tests(scripts_dir)

        assert any(f["id"] == "untested-script" and f["file"] == "scripts/do_thing.py" for f in findings)

    def test_missing_scripts_dir_is_empty(self, tmp_path):
        assert check_scripts_have_tests(tmp_path / "scripts") == []


class TestGrepHistorical:
    def test_matches_known_phrase(self):
        findings = grep_historical("SKILL.md", "This step is no longer required.\n")

        assert any(f["id"] == "historical-phrasing" and f["line"] == 1 for f in findings)

    def test_clean_text_produces_nothing(self):
        assert grep_historical("SKILL.md", "Do the thing, then stop.\n") == []


class TestCheckSkillMdLength:
    def test_long_body_with_no_references_dir_is_info(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        text = "---\nname: my-skill\n---\n" + "line\n" * 200

        findings = check_skill_md_length(skill_dir, text, frontmatter_lines=3)

        assert any(f["id"] == "long-skill-md" and f["severity"] == "info" for f in findings)

    def test_long_body_with_references_dir_is_not_flagged(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        _write(skill_dir / "references" / "details.md", "x")
        text = "---\nname: my-skill\n---\n" + "line\n" * 200

        assert check_skill_md_length(skill_dir, text, frontmatter_lines=3) == []

    def test_short_body_is_never_flagged(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        text = "---\nname: my-skill\n---\n" + "line\n" * 10

        assert check_skill_md_length(skill_dir, text, frontmatter_lines=3) == []


class TestEvaluateEndToEnd:
    def _clean_skill(self, tmp_path, name="clean-skill"):
        skill_dir = tmp_path / name
        _write(
            skill_dir / "SKILL.md",
            f"---\nname: {name}\ndescription: >\n  Use when testing.\n---\n\n"
            "See [checklist](references/checklist.md).\n",
        )
        _write(skill_dir / "references" / "checklist.md", "Nothing links onward here.\n")
        _write(skill_dir / "scripts" / "do_thing.py", "")
        _write(skill_dir / "scripts" / "test_do_thing.py", "")
        return skill_dir

    def test_clean_skill_has_no_findings(self, tmp_path):
        result = evaluate(self._clean_skill(tmp_path))

        assert result["findings"] == []
        assert result["counts"] == {"error": 0, "warn": 0, "info": 0}

    def test_missing_skill_md_raises(self, tmp_path):
        skill_dir = tmp_path / "no-skill-md"
        skill_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            evaluate(skill_dir)

    def test_main_exits_zero_on_clean_skill(self, tmp_path):
        skill_dir = self._clean_skill(tmp_path)

        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(skill_dir)], capture_output=True, text=True
        )

        assert proc.returncode == 0
        assert json.loads(proc.stdout)["counts"] == {"error": 0, "warn": 0, "info": 0}

    def test_main_exits_one_on_error_finding(self, tmp_path):
        skill_dir = tmp_path / "broken-skill"
        _write(skill_dir / "SKILL.md", "---\nname: wrong-name\n---\nbody\n")

        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(skill_dir)], capture_output=True, text=True
        )

        assert proc.returncode == 1
        assert json.loads(proc.stdout)["counts"]["error"] >= 1
