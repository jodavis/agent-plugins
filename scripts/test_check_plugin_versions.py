import subprocess
from unittest.mock import patch

import pytest

import check_plugin_versions as cpv


def make_completed_process(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def expect_run_git(responses):
    """Patch cpv.run_git to answer with the response registered for each exact args list."""

    def side_effect(args):
        key = tuple(args)
        if key not in responses:
            raise AssertionError(f"Unexpected git args: {list(key)}")
        return responses[key]

    return patch.object(cpv, "run_git", side_effect=side_effect)


def manifest_json(version):
    return f'{{"name": "x", "version": "{version}"}}'


PLUGIN_MISSING_STDERR = (
    "fatal: path 'plugins/dev-team/.claude-plugin/plugin.json' does not exist in 'HEAD'"
)


# --- find_touched_plugins ---------------------------------------------------


def test_find_touched_plugins_file_under_plugin_dir_returns_plugin_name():
    changed = ["plugins/dev-team/skills/foo/SKILL.md"]

    result = cpv.find_touched_plugins(changed)

    assert result == {"dev-team"}


def test_find_touched_plugins_multiple_files_same_plugin_returns_single_name():
    changed = [
        "plugins/dev-team/skills/foo/SKILL.md",
        "plugins/dev-team/.claude-plugin/plugin.json",
    ]

    result = cpv.find_touched_plugins(changed)

    assert result == {"dev-team"}


def test_find_touched_plugins_multiple_plugins_returns_all_names():
    changed = [
        "plugins/dev-team/skills/foo/SKILL.md",
        "plugins/other-plugin/.claude-plugin/plugin.json",
    ]

    result = cpv.find_touched_plugins(changed)

    assert result == {"dev-team", "other-plugin"}


def test_find_touched_plugins_file_directly_under_plugins_root_returns_empty():
    changed = ["plugins/README.md"]

    result = cpv.find_touched_plugins(changed)

    assert result == set()


def test_find_touched_plugins_file_outside_plugins_dir_returns_empty():
    changed = ["README.md", "scripts/check_plugin_versions.py"]

    result = cpv.find_touched_plugins(changed)

    assert result == set()


# --- compare_semver ----------------------------------------------------------


def test_compare_semver_head_greater_than_base_returns_true():
    assert cpv.compare_semver("1.4.0", "1.4.1") is True


def test_compare_semver_head_equal_to_base_returns_false():
    assert cpv.compare_semver("1.4.0", "1.4.0") is False


def test_compare_semver_head_less_than_base_returns_false():
    assert cpv.compare_semver("1.4.0", "1.3.9") is False


def test_compare_semver_invalid_head_string_raises_plugin_version_error():
    with pytest.raises(cpv.PluginVersionError):
        cpv.compare_semver("1.4.0", "not-a-version")


def test_compare_semver_invalid_base_string_raises_plugin_version_error():
    with pytest.raises(cpv.PluginVersionError):
        cpv.compare_semver("not-a-version", "1.4.0")


# --- parse_version_from_json --------------------------------------------------


def test_parse_version_from_json_valid_json_returns_version_string():
    result = cpv.parse_version_from_json(manifest_json("1.4.0"))

    assert result == "1.4.0"


def test_parse_version_from_json_missing_version_field_raises_plugin_version_error():
    with pytest.raises(cpv.PluginVersionError):
        cpv.parse_version_from_json('{"name": "x"}')


def test_parse_version_from_json_invalid_json_raises_plugin_version_error():
    with pytest.raises(cpv.PluginVersionError):
        cpv.parse_version_from_json("{not valid json")


# --- read_version_json_at_ref -------------------------------------------------


def test_read_version_json_at_ref_missing_path_returns_none():
    responses = {
        ("show", "HEAD:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            returncode=128, stderr=PLUGIN_MISSING_STDERR
        ),
    }

    with expect_run_git(responses):
        result = cpv.read_version_json_at_ref("dev-team", "HEAD")

    assert result is None


def test_read_version_json_at_ref_git_failure_raises_runtime_error():
    responses = {
        ("show", "origin/main:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            returncode=128, stderr="fatal: invalid object name 'origin/main'."
        ),
    }

    with expect_run_git(responses):
        with pytest.raises(RuntimeError):
            cpv.read_version_json_at_ref("dev-team", "origin/main")


# --- check_plugin --------------------------------------------------------------


def test_check_plugin_new_plugin_no_base_version_passes():
    responses = {
        ("show", "HEAD:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("0.1.0")
        ),
        ("show", "origin/main:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            returncode=128, stderr=PLUGIN_MISSING_STDERR
        ),
    }

    with expect_run_git(responses):
        result = cpv.check_plugin("dev-team", "origin/main")

    assert result.ok is True


def test_check_plugin_deleted_plugin_directory_passes():
    responses = {
        ("show", "HEAD:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            returncode=128, stderr=PLUGIN_MISSING_STDERR
        ),
        ("ls-tree", "-d", "--name-only", "HEAD", "plugins/dev-team"): make_completed_process(stdout=""),
    }

    with expect_run_git(responses):
        result = cpv.check_plugin("dev-team", "origin/main")

    assert result.ok is True


def test_check_plugin_missing_manifest_at_head_fails():
    responses = {
        ("show", "HEAD:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            returncode=128, stderr=PLUGIN_MISSING_STDERR
        ),
        ("ls-tree", "-d", "--name-only", "HEAD", "plugins/dev-team"): make_completed_process(
            stdout="plugins/dev-team\n"
        ),
    }

    with expect_run_git(responses):
        result = cpv.check_plugin("dev-team", "origin/main")

    assert result.ok is False


def test_check_plugin_version_unchanged_fails_with_bump_message():
    responses = {
        ("show", "HEAD:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.4.0")
        ),
        ("show", "origin/main:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.4.0")
        ),
    }

    with expect_run_git(responses):
        result = cpv.check_plugin("dev-team", "origin/main")

    assert result.ok is False
    assert "1.4.0" in result.message


def test_check_plugin_version_lowered_fails():
    responses = {
        ("show", "HEAD:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.3.0")
        ),
        ("show", "origin/main:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.4.0")
        ),
    }

    with expect_run_git(responses):
        result = cpv.check_plugin("dev-team", "origin/main")

    assert result.ok is False


def test_check_plugin_version_bumped_higher_passes():
    responses = {
        ("show", "HEAD:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.4.1")
        ),
        ("show", "origin/main:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.4.0")
        ),
    }

    with expect_run_git(responses):
        result = cpv.check_plugin("dev-team", "origin/main")

    assert result.ok is True


def test_check_plugin_invalid_semver_at_head_fails_with_parse_error_message():
    responses = {
        ("show", "HEAD:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("not-a-version")
        ),
        ("show", "origin/main:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.4.0")
        ),
    }

    with expect_run_git(responses):
        result = cpv.check_plugin("dev-team", "origin/main")

    assert result.ok is False
    assert "not-a-version" in result.message


def test_check_plugin_unparsable_base_json_treated_as_no_prior_version_passes():
    responses = {
        ("show", "HEAD:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.4.0")
        ),
        ("show", "origin/main:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout="{not valid json"
        ),
    }

    with expect_run_git(responses):
        result = cpv.check_plugin("dev-team", "origin/main")

    assert result.ok is True


# --- main ------------------------------------------------------------------------


def test_main_multiple_plugins_touched_reports_all_violations_not_just_first(capsys):
    responses = {
        ("diff", "--name-only", "origin/main", "HEAD"): make_completed_process(
            stdout="plugins/dev-team/SKILL.md\nplugins/other-plugin/SKILL.md\n"
        ),
        ("show", "HEAD:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.4.0")
        ),
        ("show", "origin/main:plugins/dev-team/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.4.0")
        ),
        ("show", "HEAD:plugins/other-plugin/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("2.0.0")
        ),
        ("show", "origin/main:plugins/other-plugin/.claude-plugin/plugin.json"): make_completed_process(
            stdout=manifest_json("1.0.0")
        ),
    }

    with expect_run_git(responses):
        exit_code = cpv.main(["--base-ref", "origin/main"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "[FAIL] dev-team" in output
    assert "[PASS] other-plugin" in output


def test_main_no_plugins_touched_exits_zero(capsys):
    responses = {
        ("diff", "--name-only", "origin/main", "HEAD"): make_completed_process(
            stdout="README.md\n"
        ),
    }

    with expect_run_git(responses):
        exit_code = cpv.main(["--base-ref", "origin/main"])

    assert exit_code == 0
