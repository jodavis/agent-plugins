#!/usr/bin/env python3
"""Runs the mechanical (Group A) checks from skill-checklist-review/references/checklist.md
against one skill directory.

Usage: check_skill_structure.py <skill-dir>

Checks:
  - frontmatter `name:` matches the directory's own name
  - frontmatter `description:` is present (and flagged if conspicuously long)
  - every file under references/ is linked from SKILL.md (no orphans)
  - no reference file links to another local file (references are one hop from SKILL.md)
  - every local file path referenced from SKILL.md or a reference file actually exists
  - every non-test script under scripts/ has a corresponding test file
  - a soft grep for historical-record phrasing ("no longer", "used to", ...), surfaced as info
    for a human to resolve against the checklist's history-free item
  - SKILL.md body length vs. a threshold when there's no references/ directory, surfaced as
    info for a human to resolve against the checklist's reference-extraction item (#15)

Prints one JSON object to stdout: {"skill": ..., "findings": [...], "counts": {...}}.
Each finding is {"id", "severity" ("error"|"warn"|"info"), "message", "file", "line"}; `line`
is null when the finding isn't anchored to one line.

Exits 1 if any finding is "error" severity, else 0. Warnings and info never affect exit status —
relay them for a human/Group-B pass, don't fail the run on them.
"""

import json
import re
import sys
from pathlib import Path

_LOCAL_EXTENSIONS = (".md", ".py", ".sh", ".mjs", ".js", ".json", ".yaml", ".yml", ".txt")
_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_HISTORICAL_PHRASES = (
    "no longer",
    "used to ",
    "previously was",
    "previously included",
    "we removed",
    "has been removed",
    "removed the",
    "deprecated",
)


def _finding(id_, severity, message, file, line=None):
    return {"id": id_, "severity": severity, "message": message, "file": file, "line": line}


def parse_frontmatter(text):
    """Returns (dict of frontmatter keys, line count consumed). Handles `key: >` folded scalars."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, 0
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, 0

    data = {}
    key, folded, buf = None, False, []
    for line in lines[1:end]:
        if folded:
            if line.strip() == "" or line.startswith((" ", "\t")):
                buf.append(line.strip())
                continue
            data[key] = " ".join(b for b in buf if b).strip()
            folded, buf = False, []
        match = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if not match:
            continue
        k, v = match.group(1), match.group(2)
        if v == ">":
            key, folded, buf = k, True, []
        else:
            data[k] = v.strip()
    if folded:
        data[key] = " ".join(b for b in buf if b).strip()
    return data, end + 1


def _looks_local(target):
    target = target.strip("\"'")
    if target.startswith(("http://", "https://", "<", "~")):
        return False
    if target.startswith(("references/", "scripts/", "assets/")) and target.endswith(_LOCAL_EXTENSIONS):
        return True
    # Cross-skill convention: a bare "<other-skill-name>/SKILL.md" reference, resolved against
    # the shared skills/ parent (see _resolve). Excludes deeper paths like "skills/x/SKILL.md",
    # which read as a pointer into another tool/plugin's own tree, not this repo's skills/.
    return target.endswith("/SKILL.md") and target.count("/") == 1


def _is_cross_skill_link(target):
    return target.endswith("/SKILL.md") and not target.startswith(("references/", "scripts/", "assets/"))


def extract_local_refs(text):
    """Returns deduped [(path, first_line_number)] for local file paths cited in markdown links
    or inline code spans."""
    seen = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in (_LINK_RE, _BACKTICK_RE):
            for m in pattern.finditer(line):
                target = m.group(1).strip("\"'")
                if _looks_local(target) and target not in seen:
                    seen[target] = lineno
    return list(seen.items())


def _true_dirname(skill_dir):
    """A display-only approximation of the on-disk directory name, for finding messages — not
    used for the match decision itself (see _frontmatter_name_matches_dir)."""
    try:
        entries = {p.name.lower(): p.name for p in skill_dir.parent.iterdir()}
    except FileNotFoundError:
        return skill_dir.name
    return entries.get(skill_dir.name.lower(), skill_dir.name)


def _frontmatter_name_matches_dir(skill_dir, name):
    """Whether `name` refers to skill_dir, compared by inode rather than by string equality.

    A case-insensitive-but-case-preserving filesystem (e.g. a macOS-host virtiofs bind mount)
    can expose the *same* directory under two different-case names in a single parent listing
    at once — confirmed empirically: `os.listdir()` on this plugin's skills/ returned both
    'work-with-github-issues' and 'work-with-GitHub-issues' for one inode in the same call,
    evidently because the directory had been looked up with inconsistent casing earlier in the
    session (e.g. a prior `find -iname`/`mv`). Picking "the" canonical name from that listing
    (the earlier approach) is non-deterministic — whichever casing the dict comprehension kept
    depends on iteration order. Comparing inodes instead sidesteps the ambiguity entirely: if
    any entry matching `name` case-insensitively shares skill_dir's inode, the frontmatter name
    is correct, full stop, regardless of which alias happened to be listed last."""
    try:
        target_ino = skill_dir.stat().st_ino
        for entry in skill_dir.parent.iterdir():
            if entry.name.lower() == name.lower():
                try:
                    if entry.stat().st_ino == target_ino:
                        return True
                except FileNotFoundError:
                    continue
        return False
    except FileNotFoundError:
        return False


def check_frontmatter(skill_dir, data):
    findings = []
    name = data.get("name")
    if not name:
        findings.append(_finding("missing-name", "error", "Frontmatter has no 'name' key.", "SKILL.md"))
    elif not _frontmatter_name_matches_dir(skill_dir, name):
        findings.append(_finding(
            "name-mismatch", "error",
            f"Frontmatter name '{name}' does not match directory name '{_true_dirname(skill_dir)}'.",
            "SKILL.md",
        ))

    description = data.get("description")
    if not description:
        findings.append(_finding(
            "missing-description", "warn",
            "No 'description' in frontmatter — this gets replaced by one generated from the "
            "skill's body, not left blank, so it can end up longer and broader-matching than "
            "intended. If this skill is meant to be dispatched only by explicit name, add a "
            "short, deliberately inert description (e.g. 'Only use when instructed.') instead "
            "of leaving the field out — see checklist Group B #2.",
            "SKILL.md",
        ))
    else:
        word_count = len(description.split())
        if word_count > 80:
            findings.append(_finding(
                "long-description", "info",
                f"Description is {word_count} words — review against checklist Group B #1 "
                "(terse, non-redundant with the name).",
                "SKILL.md",
            ))
    return findings


def _resolve(skill_dir, target):
    """A target resolves either inside this skill (references/, scripts/, ...) or, per this
    repo's cross-skill convention, as '<other-skill-name>/SKILL.md' relative to the shared
    skills/ parent directory. Try both before calling a link dangling."""
    direct = skill_dir / target
    if direct.exists():
        return direct
    sibling = skill_dir.parent / target
    if sibling.exists():
        return sibling
    return direct


def check_references(skill_dir, skill_md_text):
    findings = []
    linked_paths = set()

    for target, lineno in extract_local_refs(skill_md_text):
        linked_paths.add(target)
        if not _resolve(skill_dir, target).exists():
            if _is_cross_skill_link(target):
                findings.append(_finding(
                    "unresolved-cross-skill-link", "warn",
                    f"SKILL.md links to '{target}', not found as a sibling skill — confirm "
                    "it's a deliberate external/plugin reference, not a typo.",
                    "SKILL.md", lineno,
                ))
            else:
                findings.append(_finding(
                    "dangling-link", "error",
                    f"SKILL.md links to '{target}', which does not exist.",
                    "SKILL.md", lineno,
                ))

    references_dir = skill_dir / "references"
    if not references_dir.is_dir():
        return findings

    for ref_file in sorted(p for p in references_dir.rglob("*") if p.is_file()):
        rel = ref_file.relative_to(skill_dir).as_posix()
        if rel not in linked_paths:
            findings.append(_finding(
                "orphan-reference", "warn",
                f"'{rel}' exists under references/ but is never linked from SKILL.md.",
                rel,
            ))
            continue

        for target, lineno in extract_local_refs(ref_file.read_text()):
            findings.append(_finding(
                "reference-chain", "warn",
                f"'{rel}' links to '{target}' — references should be one hop from SKILL.md, "
                "not chained.",
                rel, lineno,
            ))
            if not _resolve(skill_dir, target).exists():
                severity = "warn" if _is_cross_skill_link(target) else "error"
                findings.append(_finding(
                    "dangling-link", severity,
                    f"'{rel}' links to '{target}', which does not exist.",
                    rel, lineno,
                ))
    return findings


def check_scripts_have_tests(scripts_dir):
    if not scripts_dir.is_dir():
        return []

    py_files = sorted(scripts_dir.glob("*.py"))
    test_names = {p.name for p in py_files if p.name.startswith("test_") or p.name.endswith("_test.py")}
    source_files = [p for p in py_files if p.name not in test_names]

    findings = []
    for src in source_files:
        candidates = {f"test_{src.stem}.py", f"{src.stem}_test.py"}
        if not candidates & test_names:
            findings.append(_finding(
                "untested-script", "warn",
                f"No test file found for 'scripts/{src.name}' (expected one of {sorted(candidates)}).",
                f"scripts/{src.name}",
            ))
    return findings


def grep_historical(rel_path, text):
    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        hit = next((p for p in _HISTORICAL_PHRASES if p in low), None)
        if hit:
            findings.append(_finding(
                "historical-phrasing", "info",
                f"Possible historical-record language ('{hit.strip()}') — resolve against "
                "checklist Group B #4 (history-free).",
                rel_path, lineno,
            ))
    return findings


_LONG_SKILL_MD_THRESHOLD = 150


def check_skill_md_length(skill_dir, text, frontmatter_lines):
    if (skill_dir / "references").is_dir():
        return []
    body_lines = len(text.splitlines()) - frontmatter_lines
    if body_lines <= _LONG_SKILL_MD_THRESHOLD:
        return []
    return [_finding(
        "long-skill-md", "info",
        f"SKILL.md body is {body_lines} lines with no references/ directory — review against "
        "checklist Group B #15 (large or rarely-needed detail belongs in a reference file, not "
        "inlined).",
        "SKILL.md",
    )]


def evaluate(skill_dir):
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"{skill_md} not found")

    text = skill_md.read_text()
    data, frontmatter_lines = parse_frontmatter(text)

    findings = []
    findings += check_frontmatter(skill_dir, data)
    findings += check_references(skill_dir, text)
    findings += check_scripts_have_tests(skill_dir / "scripts")
    findings += grep_historical("SKILL.md", text)
    findings += check_skill_md_length(skill_dir, text, frontmatter_lines)

    references_dir = skill_dir / "references"
    if references_dir.is_dir():
        for ref_file in sorted(references_dir.rglob("*.md")):
            rel = ref_file.relative_to(skill_dir).as_posix()
            findings += grep_historical(rel, ref_file.read_text())

    counts = {sev: sum(1 for f in findings if f["severity"] == sev) for sev in ("error", "warn", "info")}
    return {"skill": skill_dir.name, "findings": findings, "counts": counts}


def main():
    if len(sys.argv) != 2:
        print("Usage: check_skill_structure.py <skill-dir>", file=sys.stderr)
        sys.exit(2)

    skill_dir = Path(sys.argv[1]).resolve()
    try:
        result = evaluate(skill_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))
    sys.exit(1 if result["counts"]["error"] else 0)


if __name__ == "__main__":
    main()
