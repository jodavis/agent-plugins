"""Tests for merge_config.py.

Covers:
- parse_yaml() — the hand-rolled minimal YAML subset parser
- find_repo_root() — .git/.claude ancestor search
- load_tier() / candidate_config_paths() — tier file location
- deep_merge() — purely structural, schema-agnostic merge
- main() — end-to-end tiered merge, including error paths
"""

from pathlib import Path

import pytest

from merge_config import (
    YamlParseError,
    candidate_config_paths,
    deep_merge,
    find_repo_root,
    load_tier,
    main,
    merge_all_tiers,
    parse_yaml,
)

ADAPTIVEREMOTE_CONFIG = """\
developer-standards:
  CONTRIBUTING.md: "Code guidelines: Naming conventions, file structure, logging standards, and test conventions"
  CLAUDE.md: "Quality gates and operational conventions"
  .editorconfig: "Authoritative code style specification"

work-tracking:
  jira:
    issue-key-pattern: ADR-\\d+
    recognize-patterns:
    - Task \\d+
    - Epic \\d+
    - Jira \\d+
    task-work-item:
      type: Task
      replace-description-when: This task is added to a spec, and the current description contains initial notes
      update-description-when: Revising a spec
    feature-work-item:
      type: Epic
      update-description-when: Adding to a spec or revising a spec
      replace-description-when: Writing a spec for the first time, and the description contains initial notes
  github:
    issue-key-pattern: Issue-\\d+
    recognize-patterns:
    - "#\\\\d+"
    - Issue \\d+
    - GitHub \\d+
    bug-item:
      type: Issue

documentation:
  format: MarkDown
  architecture:
    location: In folder with related source files
    name-format: "_doc_<slug>.md"
    search: grep -rl "^Summary:" . --include="_doc_*.md"
  specs:
    location: In folder with related source files
    name-format: "_spec_<slug>.md"
    search: grep -rl "<work-item-id>" . --include="_spec_*.md"

git-repo:
  working-branches:
    task: dev/<user-alias>/<task-work-item-id>
    feature: feature/<feature-work-item-id>-<slug>
  commit:
    when: A task implementation is complete, or on each individual bug or code review comment addressed
  push:
    enabled: true
    when: Only after a full successful run of scripts/validate-build and scripts/validate-tests
  create-pr:
    enabled: true
    draft: true
    when: the working branch has been pushed and a PR does not already exist
  promote-pr:
    enabled: true
    when: All review comments are addressed and validation passes
"""


def _repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return root


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


# ---------------------------------------------------------------------------
# parse_yaml
# ---------------------------------------------------------------------------

class TestParseYaml:
    def test_empty_input_returns_empty_dict(self):
        assert parse_yaml("") == {}

    def test_only_comments_and_blank_lines_returns_empty_dict(self):
        assert parse_yaml("# a comment\n\n   \n# another\n") == {}

    def test_flat_map(self):
        assert parse_yaml("a: 1\nb: two\n") == {"a": "1", "b": "two"}

    def test_nested_map(self):
        text = "a:\n  b: 1\n  c: 2\n"
        assert parse_yaml(text) == {"a": {"b": "1", "c": "2"}}

    def test_deeply_nested_map(self):
        text = "a:\n  b:\n    c:\n      d: value\n"
        assert parse_yaml(text) == {"a": {"b": {"c": {"d": "value"}}}}

    def test_empty_value_after_colon_is_none(self):
        assert parse_yaml("key:\n") == {"key": None}
        assert parse_yaml("key:\nother: 1\n") == {"key": None, "other": "1"}

    def test_list_of_scalars_dash_aligned_with_key(self):
        text = "items:\n- a\n- b\n- c\n"
        assert parse_yaml(text) == {"items": ["a", "b", "c"]}

    def test_list_of_scalars_indented_deeper_than_key(self):
        text = "items:\n  - a\n  - b\n"
        assert parse_yaml(text) == {"items": ["a", "b"]}

    def test_list_nested_under_map_key_dash_aligned(self):
        text = "parent:\n  child:\n  - a\n  - b\n  sibling: 1\n"
        assert parse_yaml(text) == {"parent": {"child": ["a", "b"], "sibling": "1"}}

    def test_list_of_maps_inline_style(self):
        text = "items:\n- name: first\n  value: 1\n- name: second\n  value: 2\n"
        assert parse_yaml(text) == {
            "items": [
                {"name": "first", "value": "1"},
                {"name": "second", "value": "2"},
            ]
        }

    def test_quoted_scalars_single_and_double(self):
        text = "a: \"double\"\nb: 'single'\n"
        assert parse_yaml(text) == {"a": "double", "b": "single"}

    def test_hash_inside_double_quotes_not_treated_as_comment(self):
        text = 'items:\n- "#comment-looking-value"\n- plain\n'
        assert parse_yaml(text) == {"items": ["#comment-looking-value", "plain"]}

    def test_full_line_comment_ignored(self):
        text = "# leading comment\na: 1\n"
        assert parse_yaml(text) == {"a": "1"}

    def test_trailing_comment_stripped(self):
        text = "a: 1  # trailing comment\n"
        assert parse_yaml(text) == {"a": "1"}

    def test_boolean_true_and_false(self):
        text = "enabled: true\ndisabled: false\n"
        assert parse_yaml(text) == {"enabled": True, "disabled": False}

    def test_null_and_tilde_are_none(self):
        text = "a: null\nb: ~\n"
        assert parse_yaml(text) == {"a": None, "b": None}

    def test_value_with_unquoted_colon_not_followed_by_space_is_scalar(self):
        text = "url: http://example.com\n"
        assert parse_yaml(text) == {"url": "http://example.com"}

    def test_tabs_in_indentation_raise(self):
        with pytest.raises(YamlParseError):
            parse_yaml("a:\n\tb: 1\n")

    def test_inline_value_and_nested_block_raises(self):
        with pytest.raises(YamlParseError):
            parse_yaml("a: 1\n  b: 2\n")

    def test_top_level_list_raises(self):
        with pytest.raises(YamlParseError):
            parse_yaml("- a\n- b\n")

    def test_line_without_colon_raises_with_line_number(self):
        with pytest.raises(YamlParseError) as exc_info:
            parse_yaml("a: 1\nnot a valid line\n")
        assert exc_info.value.line_no == 2

    def test_adaptiveremote_sample_config_parses_end_to_end(self):
        result = parse_yaml(ADAPTIVEREMOTE_CONFIG)
        assert set(result["work-tracking"].keys()) == {"jira", "github"}
        assert result["work-tracking"]["github"]["recognize-patterns"] == [
            "#\\d+",
            "Issue \\d+",
            "GitHub \\d+",
        ]
        assert result["work-tracking"]["jira"]["feature-work-item"]["type"] == "Epic"
        assert result["git-repo"]["push"]["enabled"] is True
        assert result["git-repo"]["create-pr"]["draft"] is True


# ---------------------------------------------------------------------------
# parse_yaml — double/single-quoted scalar escape sequences
# ---------------------------------------------------------------------------

class TestParseYamlEscapes:
    def test_double_backslash_unescapes_to_single_backslash(self):
        # "#\\d+" in the YAML source (an escaped backslash followed by literal
        # "d+") must parse to the regex pattern #\d+ (one backslash) — this is
        # the case a hand-written regex like an issue-key-pattern needs.
        text = 'pattern: "#\\\\d+"\n'
        assert parse_yaml(text) == {"pattern": "#\\d+"}

    def test_escaped_double_quote(self):
        text = r'a: "say \"hi\""' + "\n"
        assert parse_yaml(text) == {"a": 'say "hi"'}

    def test_escaped_newline_tab_and_carriage_return(self):
        text = r'a: "line1\nline2"' + "\n" + r'b: "a\tb"' + "\n" + r'c: "a\rb"' + "\n"
        result = parse_yaml(text)
        assert result == {"a": "line1\nline2", "b": "a\tb", "c": "a\rb"}

    def test_escaped_forward_slash(self):
        text = r'a: "a\/b"' + "\n"
        assert parse_yaml(text) == {"a": "a/b"}

    def test_unsupported_escape_sequence_raises(self):
        with pytest.raises(YamlParseError):
            parse_yaml('a: "#\\d+"\n')

    def test_trailing_backslash_in_double_quoted_scalar_raises(self):
        with pytest.raises(YamlParseError):
            parse_yaml('a: "abc\\"\n')

    def test_single_quoted_scalar_does_not_process_backslash_escapes(self):
        # Single-quoted YAML scalars have no backslash escaping at all —
        # a backslash is always literal.
        text = "a: 'a\\nb'\n"
        assert parse_yaml(text) == {"a": "a\\nb"}

    def test_single_quoted_doubled_quote_is_literal_quote(self):
        text = "a: 'can''t'\n"
        assert parse_yaml(text) == {"a": "can't"}

    def test_adaptiveremote_github_recognize_pattern_unescapes_correctly(self):
        # Mirrors the real-world case this test class exists for: the shipped
        # AdaptiveRemote config quotes "#\\d+" so the final regex is #\d+.
        result = parse_yaml(ADAPTIVEREMOTE_CONFIG)
        assert result["work-tracking"]["github"]["recognize-patterns"][0] == "#\\d+"


# ---------------------------------------------------------------------------
# parse_yaml — literal (|) block scalars
# ---------------------------------------------------------------------------

class TestParseYamlBlockScalar:
    def test_basic_literal_block_scalar(self):
        text = "key: |\n  line one\n  line two\nafter: 1\n"
        assert parse_yaml(text) == {"key": "line one\nline two\n", "after": "1"}

    def test_default_chomping_keeps_single_trailing_newline(self):
        text = "key: |\n  content\n\n\nafter: 1\n"
        result = parse_yaml(text)
        assert result["key"] == "content\n"
        assert result["after"] == "1"

    def test_strip_chomping_removes_trailing_newlines(self):
        text = "key: |-\n  content\n\n\nafter: 1\n"
        result = parse_yaml(text)
        assert result["key"] == "content"
        assert result["after"] == "1"

    def test_keep_chomping_preserves_trailing_blank_lines(self):
        text = "key: |+\n  line one\n  line two\n\n\nafter: 1\n"
        result = parse_yaml(text)
        assert result["key"] == "line one\nline two\n\n\n"
        assert result["after"] == "1"

    def test_explicit_indent_indicator(self):
        text = "key: |2\n    extra indent kept\n  after strip\nafter: 1\n"
        result = parse_yaml(text)
        # parent indent 0 + explicit indent 2 => content indent 2
        assert result["key"] == "  extra indent kept\nafter strip\n"
        assert result["after"] == "1"

    def test_explicit_indent_before_and_after_chomping_indicator(self):
        assert parse_yaml("key: |2-\n    a\n  b\n") == {"key": "  a\nb"}
        assert parse_yaml("key: |-2\n    a\n  b\n") == {"key": "  a\nb"}

    def test_blank_lines_within_block_content_preserved(self):
        text = "key: |\n  first\n\n  third\nafter: 1\n"
        result = parse_yaml(text)
        assert result["key"] == "first\n\nthird\n"
        assert result["after"] == "1"

    def test_block_scalar_at_end_of_file(self):
        text = "key: |\n  only content\n"
        assert parse_yaml(text) == {"key": "only content\n"}

    def test_empty_block_scalar(self):
        text = "key: |\nafter: 1\n"
        assert parse_yaml(text) == {"key": "", "after": "1"}

    def test_hash_characters_preserved_literally_in_block_content(self):
        text = "key: |\n  # not a comment\n  value #still not a comment\n"
        assert parse_yaml(text) == {"key": "# not a comment\nvalue #still not a comment\n"}

    def test_tabs_in_block_content_indentation_raise(self):
        with pytest.raises(YamlParseError):
            parse_yaml("key: |\n  a\n\tb\n")

    def test_block_scalar_nested_under_map_key(self):
        text = "parent:\n  key: |\n    nested content\n  sibling: 1\n"
        assert parse_yaml(text) == {"parent": {"key": "nested content\n", "sibling": "1"}}

    def test_block_scalar_indentation_relative_to_own_first_line_not_parent_indent(self):
        # The key sits at indent 2 ("  key: |") but its block content starts at
        # indent 6; only the block's own first-line indent (6) should be stripped,
        # not the key's generic entry indent (2) — deeper-indented later lines keep
        # their extra indentation as literal content.
        text = "parent:\n  key: |\n      first line\n        more indented\n  sibling: 1\n"
        result = parse_yaml(text)
        assert result == {
            "parent": {
                "key": "first line\n  more indented\n",
                "sibling": "1",
            }
        }

    def test_git_repo_push_when_as_realistic_block_scalar(self):
        text = (
            "git-repo:\n"
            "  push:\n"
            "    enabled: true\n"
            "    when: |\n"
            "      Only after a full successful run of:\n"
            "        scripts/validate-build\n"
            "        scripts/validate-tests\n"
            "  user-alias: claude\n"
        )
        result = parse_yaml(text)
        assert result["git-repo"]["push"]["when"] == (
            "Only after a full successful run of:\n  scripts/validate-build\n  scripts/validate-tests\n"
        )
        assert result["git-repo"]["push"]["enabled"] is True
        assert result["git-repo"]["user-alias"] == "claude"


# ---------------------------------------------------------------------------
# find_repo_root
# ---------------------------------------------------------------------------

class TestFindRepoRoot:
    def test_finds_git_dir(self, tmp_path):
        root = tmp_path / "repo"
        (root / ".git").mkdir(parents=True)
        assert find_repo_root(root) == root

    def test_finds_claude_dir(self, tmp_path):
        root = tmp_path / "repo"
        (root / ".claude").mkdir(parents=True)
        assert find_repo_root(root) == root

    def test_walks_up_from_nested_cwd(self, tmp_path):
        root = tmp_path / "repo"
        nested = root / "src" / "deeply" / "nested"
        nested.mkdir(parents=True)
        (root / ".git").mkdir()
        assert find_repo_root(nested) == root

    def test_raises_when_nothing_found(self, tmp_path, monkeypatch):
        # tmp_path lives under the real user home, which itself has a .claude
        # directory — stub is_dir() so the walk never finds a real ancestor.
        monkeypatch.setattr(Path, "is_dir", lambda self: False)
        isolated = tmp_path / "no-repo-here"
        with pytest.raises(RuntimeError):
            find_repo_root(isolated)


# ---------------------------------------------------------------------------
# candidate_config_paths / load_tier
# ---------------------------------------------------------------------------

class TestCandidateConfigPaths:
    def test_four_tiers_in_ascending_precedence_order(self, tmp_path, monkeypatch):
        home = _isolate_home(monkeypatch, tmp_path)
        root = _repo_root(tmp_path)
        paths = candidate_config_paths(root)
        assert len(paths) == 4
        assert paths[0].name == "default-config.yaml"
        assert paths[1] == home / ".dev-team" / "config.yaml"
        assert paths[2] == root / ".dev-team" / "config.yaml"
        assert paths[3] == root / ".dev-team" / "config.local.yaml"


class TestLoadTier:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert load_tier(tmp_path / "does-not-exist.yaml") == {}

    def test_existing_file_parsed(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("a: 1\n", encoding="utf-8")
        assert load_tier(path) == {"a": "1"}

    def test_malformed_file_error_includes_path(self, tmp_path):
        path = tmp_path / "broken.yaml"
        path.write_text("a:\n\tb: 1\n", encoding="utf-8")
        with pytest.raises(YamlParseError) as exc_info:
            load_tier(path)
        assert str(path) in str(exc_info.value)


# ---------------------------------------------------------------------------
# deep_merge
# ---------------------------------------------------------------------------

class TestDeepMerge:
    def test_scalar_override_replaces_base(self):
        assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_new_key_in_override_is_added(self):
        assert deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_nested_dict_merges_recursively_preserving_unset_keys(self):
        base = {
            "work-tracking": {
                "jira": {"issue-key-pattern": "ADR-\\d+"},
                "github": {"issue-key-pattern": "Issue-\\d+"},
            }
        }
        override = {"work-tracking": {"jira": {"issue-key-pattern": "PROJ-\\d+"}}}
        result = deep_merge(base, override)
        assert result["work-tracking"]["jira"]["issue-key-pattern"] == "PROJ-\\d+"
        assert result["work-tracking"]["github"]["issue-key-pattern"] == "Issue-\\d+"

    def test_git_repo_push_flag_merges_without_special_casing(self):
        base = {"git-repo": {"push": {"enabled": True, "when": "default"}}}
        override = {"git-repo": {"push": {"enabled": False}}}
        result = deep_merge(base, override)
        assert result["git-repo"]["push"] == {"enabled": False, "when": "default"}

    def test_list_replaced_wholesale_not_concatenated(self):
        base = {"recognize-patterns": ["a", "b"]}
        override = {"recognize-patterns": ["c"]}
        assert deep_merge(base, override) == {"recognize-patterns": ["c"]}

    def test_null_override_replaces_dict_default(self):
        base = {"developer-standards": {"README.md": "desc"}}
        override = {"developer-standards": None}
        assert deep_merge(base, override) == {"developer-standards": None}

    def test_type_mismatch_override_replaces(self):
        assert deep_merge({"a": {"b": 1}}, {"a": "scalar"}) == {"a": "scalar"}

    def test_inputs_not_mutated(self):
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        deep_merge(base, override)
        assert base == {"a": {"b": 1}}
        assert override == {"a": {"c": 2}}

    def test_merge_all_tiers_reduces_left_to_right(self):
        tiers = [{"a": 1, "b": 1}, {"b": 2}, {"c": 3}]
        assert merge_all_tiers(tiers) == {"a": 1, "b": 2, "c": 3}


# ---------------------------------------------------------------------------
# main() end-to-end
# ---------------------------------------------------------------------------

class TestMain:
    def test_shipped_default_alone_produces_populated_developer_standards_and_null_work_tracking(
        self, tmp_path, monkeypatch, capsys
    ):
        _isolate_home(monkeypatch, tmp_path)
        root = _repo_root(tmp_path)

        exit_code = main(["--repo-root", str(root)])

        assert exit_code == 0
        import json

        merged = json.loads(capsys.readouterr().out)
        assert "CONTRIBUTING.md" in merged["developer-standards"]
        assert merged["work-tracking"] is None
        assert merged["git-repo"]["user-alias"] == "claude"

    def test_missing_optional_tiers_ok(self, tmp_path, monkeypatch, capsys):
        _isolate_home(monkeypatch, tmp_path)
        root = _repo_root(tmp_path)
        (root / ".dev-team").mkdir()
        (root / ".dev-team" / "config.yaml").write_text(
            "documentation:\n  architecture:\n    location: docs2/\n", encoding="utf-8"
        )

        exit_code = main(["--repo-root", str(root)])

        assert exit_code == 0
        import json

        merged = json.loads(capsys.readouterr().out)
        assert merged["documentation"]["architecture"]["location"] == "docs2/"
        assert merged["documentation"]["format"] == "Markdown"

    def test_work_tracking_jira_key_overridden_while_github_survives_from_lower_tier(
        self, tmp_path, monkeypatch, capsys
    ):
        home = _isolate_home(monkeypatch, tmp_path)
        root = _repo_root(tmp_path)
        (home / ".dev-team").mkdir()
        (home / ".dev-team" / "config.yaml").write_text(
            "work-tracking:\n"
            "  jira:\n"
            "    issue-key-pattern: OLD-\\d+\n"
            "  github:\n"
            "    issue-key-pattern: Issue-\\d+\n",
            encoding="utf-8",
        )
        (root / ".dev-team").mkdir()
        (root / ".dev-team" / "config.yaml").write_text(
            "work-tracking:\n  jira:\n    issue-key-pattern: ADR-\\d+\n",
            encoding="utf-8",
        )

        exit_code = main(["--repo-root", str(root)])

        assert exit_code == 0
        import json

        merged = json.loads(capsys.readouterr().out)
        assert merged["work-tracking"]["jira"]["issue-key-pattern"] == "ADR-\\d+"
        assert merged["work-tracking"]["github"]["issue-key-pattern"] == "Issue-\\d+"

    def test_developer_standards_nulled_out_by_project_tier(self, tmp_path, monkeypatch, capsys):
        _isolate_home(monkeypatch, tmp_path)
        root = _repo_root(tmp_path)
        (root / ".dev-team").mkdir()
        (root / ".dev-team" / "config.yaml").write_text("developer-standards:\n", encoding="utf-8")

        exit_code = main(["--repo-root", str(root)])

        assert exit_code == 0
        import json

        merged = json.loads(capsys.readouterr().out)
        assert merged["developer-standards"] is None

    def test_local_tier_beats_project_tier_beats_machine_tier(self, tmp_path, monkeypatch, capsys):
        home = _isolate_home(monkeypatch, tmp_path)
        root = _repo_root(tmp_path)
        (home / ".dev-team").mkdir()
        (home / ".dev-team" / "config.yaml").write_text("git-repo:\n  user-alias: machine\n", encoding="utf-8")
        (root / ".dev-team").mkdir()
        (root / ".dev-team" / "config.yaml").write_text("git-repo:\n  user-alias: project\n", encoding="utf-8")
        (root / ".dev-team" / "config.local.yaml").write_text("git-repo:\n  user-alias: local\n", encoding="utf-8")

        exit_code = main(["--repo-root", str(root)])

        assert exit_code == 0
        import json

        merged = json.loads(capsys.readouterr().out)
        assert merged["git-repo"]["user-alias"] == "local"

    def test_malformed_yaml_exits_1_with_file_in_stderr(self, tmp_path, monkeypatch, capsys):
        _isolate_home(monkeypatch, tmp_path)
        root = _repo_root(tmp_path)
        (root / ".dev-team").mkdir()
        bad_file = root / ".dev-team" / "config.yaml"
        bad_file.write_text("a:\n\tb: 1\n", encoding="utf-8")

        exit_code = main(["--repo-root", str(root)])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert str(bad_file) in captured.err
        assert captured.out == ""

    def test_repo_root_not_found_exits_1(self, tmp_path, monkeypatch, capsys):
        _isolate_home(monkeypatch, tmp_path)
        isolated = tmp_path / "no-repo-here"
        isolated.mkdir()
        monkeypatch.setattr("merge_config.find_repo_root", lambda: (_ for _ in ()).throw(RuntimeError("not found")))

        exit_code = main([])

        assert exit_code == 1
        assert "Error:" in capsys.readouterr().err

    def test_adaptiveremote_config_as_project_tier_end_to_end(self, tmp_path, monkeypatch, capsys):
        _isolate_home(monkeypatch, tmp_path)
        root = _repo_root(tmp_path)
        (root / ".dev-team").mkdir()
        (root / ".dev-team" / "config.yaml").write_text(ADAPTIVEREMOTE_CONFIG, encoding="utf-8")

        exit_code = main(["--repo-root", str(root)])

        assert exit_code == 0
        import json

        merged = json.loads(capsys.readouterr().out)
        assert merged["work-tracking"]["github"]["recognize-patterns"][0] == "#\\d+"
        assert merged["git-repo"]["working-branches"]["task"] == "dev/<user-alias>/<task-work-item-id>"
        assert merged["git-repo"]["user-alias"] == "claude"  # inherited from shipped default
        assert merged["git-repo"]["push"]["when"].startswith("Only after a full successful run")
