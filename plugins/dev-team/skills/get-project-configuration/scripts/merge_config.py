#!/usr/bin/env python3
"""Merge tiered project configuration YAML files into a single JSON document.

Usage: merge_config.py [--repo-root <path>]

Prints the merged config as JSON to stdout on success (exit 0).
Prints "Error: ..." to stderr and exits 1 on any failure.

Tiers, in ascending precedence:
  1. assets/default-config.yaml   (shipped with this skill)
  2. ~/.dev-team/config.yaml      (machine-level)
  3. <repo-root>/.dev-team/config.yaml        (project-level, committed)
  4. <repo-root>/.dev-team/config.local.yaml  (project-level, gitignored)

Merging is purely structural: dicts are merged recursively by key; any other
value (scalar, list, None, or a type mismatch) is replaced wholesale by the
higher-precedence tier. Beyond that, this script has no knowledge of what any
key means — semantic interpretation of the merged result is left to the
caller — with one deliberate exception: `developer-standards` entries marked
"If this file exists, read it — ..." are checked against the filesystem after
merging, so callers never see a soft entry for a file that doesn't exist.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent / "assets"
DEFAULT_CONFIG_ASSET = ASSETS_DIR / "default-config.yaml"

SOFT_FILE_PREFIX = "If this file exists, read it — "

Entry = tuple[int, int, str]  # (line_no, indent, content)


class YamlParseError(Exception):
    def __init__(self, path: Path, line_no: int, message: str):
        super().__init__(f"{path}:{line_no}: {message}")
        self.path = path
        self.line_no = line_no
        self.message = message


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default: cwd) until a directory containing .git or .claude is found."""
    current = (start or Path(os.getcwd())).resolve()
    while True:
        if (current / ".git").is_dir() or (current / ".claude").is_dir():
            return current
        parent = current.parent
        if parent == current:
            raise RuntimeError(
                f"Could not locate repo root: no .git or .claude directory found "
                f"in any ancestor of {(start or Path(os.getcwd())).resolve()}"
            )
        current = parent


def candidate_config_paths(repo_root: Path) -> list[Path]:
    """The 4 config tiers, in ascending precedence."""
    return [
        DEFAULT_CONFIG_ASSET,
        Path.home() / ".dev-team" / "config.yaml",
        repo_root / ".dev-team" / "config.yaml",
        repo_root / ".dev-team" / "config.local.yaml",
    ]


def _is_list_marker(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _strip_comment(line: str) -> str:
    """Strip a trailing '#' comment, but not one inside an open quote."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
    return line


def _split_key_value(content: str) -> tuple[str, str] | None:
    """Split 'key: value' / 'key:' respecting quotes.
    Returns None if there is no unquoted colon followed by a space or end-of-line."""
    in_single = False
    in_double = False
    for i, ch in enumerate(content):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            if i + 1 == len(content) or content[i + 1] == " ":
                return content[:i], content[i + 1 :]
    return None


def _match_block_scalar_indicator(value_raw: str) -> tuple[str, int | None] | None:
    """Match a literal block scalar indicator ('|', '|-', '|+', '|2', '|2-', '|-2', ...).
    Returns (chomping, explicit_indent) or None if `value_raw` isn't one. Folded ('>')
    indicators are not recognised here and fall through to being parsed as plain scalars."""
    if not value_raw.startswith("|"):
        return None
    suffix = value_raw[1:]
    if len(suffix) > 2:
        return None
    chomping = "clip"
    indent: int | None = None
    for ch in suffix:
        if ch in "+-" and chomping == "clip":
            chomping = "keep" if ch == "+" else "strip"
        elif ch in "123456789" and indent is None:
            indent = int(ch)
        else:
            return None
    return chomping, indent


def _parse_block_scalar_literal(
    raw_lines: list[str],
    header_line_no: int,
    parent_indent: int,
    chomping: str,
    explicit_indent: int | None,
) -> tuple[str, int]:
    """Parse a literal ('|') block scalar. `header_line_no` is the 1-indexed line
    number of the 'key: |' line; content is read directly from `raw_lines` (bypassing
    the comment-stripped, blank-dropped Entry list) since block scalar content must
    preserve blank lines and '#' characters literally. Returns (content,
    last_consumed_line_no) — the latter equals `header_line_no` if the block is empty."""
    content_indent = parent_indent + explicit_indent if explicit_indent is not None else None
    collected: list[str] = []
    last_consumed = header_line_no
    idx = header_line_no  # raw_lines is 0-indexed; this is the line after the header
    while idx < len(raw_lines):
        line = raw_lines[idx]
        is_blank = line.strip(" ") == ""
        line_indent = 0 if is_blank else len(line) - len(line.lstrip(" "))

        if content_indent is None:
            if is_blank:
                idx += 1
                continue
            if line_indent <= parent_indent:
                break
            content_indent = line_indent

        if not is_blank and line_indent < content_indent:
            break

        collected.append("" if is_blank else line[content_indent:])
        last_consumed = idx + 1
        idx += 1

    if not collected:
        return "", last_consumed

    joined = "\n".join(collected) + "\n"
    if chomping == "strip":
        return joined.rstrip("\n"), last_consumed
    if chomping == "keep":
        return joined, last_consumed
    return joined.rstrip("\n") + "\n", last_consumed


_DOUBLE_QUOTE_ESCAPES = {
    "\\": "\\",
    '"': '"',
    "/": "/",
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "v": "\v",
}


def _unescape_double_quoted(inner: str, path: Path, line_no: int) -> str:
    """Process YAML double-quoted scalar escapes. `inner` excludes the surrounding
    quotes. Supports the common single-character escapes (\\\\, \\", \\/, \\n, \\t,
    \\r, \\0, \\a, \\b, \\f, \\v) — a literal backslash must be written as \\\\.
    Unicode escapes (\\xXX, \\uXXXX, \\UXXXXXXXX) and the rarer named escapes
    (\\e, \\N, \\_, \\L, \\P) are not supported."""
    result: list[str] = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch != "\\":
            result.append(ch)
            i += 1
            continue
        if i + 1 >= len(inner):
            raise YamlParseError(path, line_no, "trailing backslash in double-quoted scalar")
        esc = inner[i + 1]
        if esc not in _DOUBLE_QUOTE_ESCAPES:
            raise YamlParseError(
                path, line_no, f"unsupported escape sequence '\\{esc}' in double-quoted scalar"
            )
        result.append(_DOUBLE_QUOTE_ESCAPES[esc])
        i += 2
    return "".join(result)


def _parse_scalar(raw: str, path: Path, line_no: int):
    raw = raw.strip()
    if raw == "" or raw == "null" or raw == "~":
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return _unescape_double_quoted(raw[1:-1], path, line_no)
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        # Single-quoted scalars have no backslash escaping; '' is a literal quote.
        return raw[1:-1].replace("''", "'")
    return raw


def _build_entries(text: str, path: Path) -> list[Entry]:
    entries: list[Entry] = []
    for line_no, raw_line in enumerate(text.split("\n"), start=1):
        leading = raw_line[: len(raw_line) - len(raw_line.lstrip(" \t"))]
        if "\t" in leading:
            raise YamlParseError(path, line_no, "tabs are not allowed in indentation")
        stripped = _strip_comment(raw_line).rstrip()
        if stripped.strip() == "":
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        entries.append((line_no, indent, stripped.strip()))
    return entries


def _parse_map(
    entries: list[Entry], i: int, indent: int, path: Path, raw_lines: list[str]
) -> tuple[dict, int]:
    result: dict = {}
    while i < len(entries):
        line_no, entry_indent, content = entries[i]
        if entry_indent < indent:
            break
        if entry_indent > indent:
            raise YamlParseError(path, line_no, f"unexpected indentation (expected {indent})")
        if _is_list_marker(content):
            raise YamlParseError(path, line_no, "expected 'key: value', found a list item")

        split = _split_key_value(content)
        if split is None:
            raise YamlParseError(path, line_no, f"expected 'key: value' or 'key:', got: {content!r}")
        key = _parse_scalar(split[0], path, line_no)
        value_raw = split[1].strip()

        block = _match_block_scalar_indicator(value_raw)
        if block is not None:
            chomping, explicit_indent = block
            scalar, last_consumed = _parse_block_scalar_literal(
                raw_lines, line_no, indent, chomping, explicit_indent
            )
            result[key] = scalar
            i += 1
            while i < len(entries) and entries[i][0] <= last_consumed:
                i += 1
            continue

        i += 1

        if value_raw != "":
            if i < len(entries) and entries[i][1] > indent:
                raise YamlParseError(
                    path, entries[i][0], f"key {key!r} has both an inline value and a nested block"
                )
            result[key] = _parse_scalar(value_raw, path, line_no)
            continue

        if i >= len(entries):
            result[key] = None
            continue

        next_indent, next_content = entries[i][1], entries[i][2]
        if next_indent > indent:
            if _is_list_marker(next_content):
                value, i = _parse_list(entries, i, next_indent, path, raw_lines)
            else:
                value, i = _parse_map(entries, i, next_indent, path, raw_lines)
            result[key] = value
        elif next_indent == indent and _is_list_marker(next_content):
            # YAML allows list items dash-aligned with their own key.
            value, i = _parse_list(entries, i, indent, path, raw_lines)
            result[key] = value
        else:
            result[key] = None
    return result, i


def _parse_list(
    entries: list[Entry], i: int, indent: int, path: Path, raw_lines: list[str]
) -> tuple[list, int]:
    result: list = []
    while i < len(entries):
        line_no, entry_indent, content = entries[i]
        if entry_indent < indent:
            break
        if entry_indent > indent:
            raise YamlParseError(path, line_no, f"unexpected indentation (expected {indent})")
        if not _is_list_marker(content):
            break

        rest = content[1:].lstrip()
        i += 1

        if rest == "":
            if i < len(entries) and entries[i][1] > indent:
                nested_indent = entries[i][1]
                if _is_list_marker(entries[i][2]):
                    value, i = _parse_list(entries, i, nested_indent, path, raw_lines)
                else:
                    value, i = _parse_map(entries, i, nested_indent, path, raw_lines)
            else:
                value = None
            result.append(value)
            continue

        split = _split_key_value(rest)
        if split is None:
            result.append(_parse_scalar(rest, path, line_no))
            continue

        # "- key: value" / "- key:" starts a map item; sibling keys of the same
        # item are dash-aligned two columns in from the marker.
        item_indent = indent + 2
        key = _parse_scalar(split[0], path, line_no)
        first_value_raw = split[1].strip()
        if first_value_raw != "":
            first_value = _parse_scalar(first_value_raw, path, line_no)
        elif i < len(entries) and entries[i][1] > item_indent:
            nested_indent = entries[i][1]
            if _is_list_marker(entries[i][2]):
                first_value, i = _parse_list(entries, i, nested_indent, path, raw_lines)
            else:
                first_value, i = _parse_map(entries, i, nested_indent, path, raw_lines)
        else:
            first_value = None
        rest_of_item, i = _parse_map(entries, i, item_indent, path, raw_lines)
        item = {key: first_value}
        item.update(rest_of_item)
        result.append(item)
    return result, i


def parse_yaml(text: str, path: Path = Path("<string>")) -> dict:
    """Parse a minimal YAML subset: nested maps, lists of scalars/maps, quoted/plain
    scalars, booleans, full-line and trailing comments (not inside quotes), blank
    lines, empty-value-after-colon -> None, and literal (|) block scalars in map
    values. Double-quoted scalars process the common backslash escapes (see
    `_unescape_double_quoted`); single-quoted scalars only recognise '' as a
    literal quote and otherwise treat backslash as a plain character.

    Does NOT support anchors, folded block scalars (>), block scalars as list items,
    flow style ([]/{}), or multi-document files.
    """
    entries = _build_entries(text, path)
    if not entries:
        return {}
    if _is_list_marker(entries[0][2]):
        raise YamlParseError(path, entries[0][0], "top-level YAML document must be a map")
    raw_lines = text.split("\n")
    result, next_i = _parse_map(entries, 0, entries[0][1], path, raw_lines)
    if next_i != len(entries):
        line_no, indent, _content = entries[next_i]
        raise YamlParseError(path, line_no, f"unexpected indentation (expected {entries[0][1]})")
    return result


def deep_merge(base, override):
    """Purely structural, schema-agnostic merge: dicts merge recursively by key;
    everything else (scalars, lists, None, type mismatches) is replaced wholesale
    by `override`."""
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for key, value in override.items():
            result[key] = deep_merge(result[key], value) if key in result else value
        return result
    return override


def merge_all_tiers(tier_dicts: list[dict]) -> dict:
    merged: dict = {}
    for tier in tier_dicts:
        merged = deep_merge(merged, tier)
    return merged


def load_tier(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    return parse_yaml(text, path)


def _resolve_config_path(repo_root: Path, rel: str) -> Path:
    """Resolve a path-like config value: `~`-relative to the user's home directory,
    otherwise relative to `repo_root` — per get-project-configuration's documented
    path convention."""
    if rel.startswith("~"):
        return Path.home() / rel[1:].lstrip("/")
    return repo_root / rel


def apply_developer_standards_filter(merged: dict, repo_root: Path) -> dict:
    """Pre-resolve `developer-standards` entries against the filesystem: an entry whose
    description starts with `SOFT_FILE_PREFIX` is dropped if the file doesn't exist, or
    kept with the prefix stripped if it does. Entries without that prefix (required —
    expected to exist) are left untouched either way; a missing required entry is a
    project config pointing at something that isn't there, for the caller to note, not
    something this function silently drops."""
    developer_standards = merged.get("developer-standards")
    if not isinstance(developer_standards, dict):
        return merged

    filtered: dict = {}
    for filename, description in developer_standards.items():
        if isinstance(description, str) and description.startswith(SOFT_FILE_PREFIX):
            if not _resolve_config_path(repo_root, filename).is_file():
                continue
            filtered[filename] = description[len(SOFT_FILE_PREFIX):]
        else:
            filtered[filename] = description

    merged["developer-standards"] = filtered
    return merged


def build_merged_config(repo_root: Path | None = None) -> dict:
    """Resolve `repo_root` (if not given), merge all 4 config tiers, and apply the
    `developer-standards` filesystem pre-filter. Raises `YamlParseError` or
    `RuntimeError` on failure — same errors `main()` reports."""
    resolved_root = repo_root.resolve() if repo_root else find_repo_root()
    tiers = [load_tier(p) for p in candidate_config_paths(resolved_root)]
    merged = merge_all_tiers(tiers)
    return apply_developer_standards_filter(merged, resolved_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    try:
        repo_root = Path(args.repo_root) if args.repo_root else None
        merged = build_merged_config(repo_root)
    except (YamlParseError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(merged, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
