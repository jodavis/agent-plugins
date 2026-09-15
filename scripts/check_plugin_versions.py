"""
check_plugin_versions.py — CI gate: require a plugin's version to be bumped
whenever a pull request touches files under that plugin's directory.

Usage:
    python3 check_plugin_versions.py --base-ref origin/main
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass

PLUGIN_FILE_RE = re.compile(r"^plugins/([^/]+)/")
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
PLUGIN_MANIFEST_TEMPLATE = "plugins/{name}/.claude-plugin/plugin.json"


class PluginVersionError(Exception):
    """Raised when a plugin's version field cannot be parsed or compared."""


@dataclass
class CheckResult:
    plugin: str
    ok: bool
    message: str


def run_git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def get_changed_files(base_ref: str) -> list[str]:
    result = run_git(["diff", "--name-only", base_ref, "HEAD"])
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def find_touched_plugins(changed_files: list[str]) -> set[str]:
    plugins = set()
    for path in changed_files:
        match = PLUGIN_FILE_RE.match(path)
        if match:
            plugins.add(match.group(1))
    return plugins


def plugin_dir_exists_at_ref(plugin_name: str, ref: str) -> bool:
    result = run_git(["ls-tree", "-d", "--name-only", ref, f"plugins/{plugin_name}"])
    return result.returncode == 0 and bool(result.stdout.strip())


def read_version_json_at_ref(plugin_name: str, ref: str) -> str | None:
    path = PLUGIN_MANIFEST_TEMPLATE.format(name=plugin_name)
    result = run_git(["show", f"{ref}:{path}"])
    if result.returncode == 0:
        return result.stdout
    stderr = result.stderr.lower()
    if "does not exist in" in stderr or "exists on disk, but not in" in stderr:
        return None
    raise RuntimeError(f"git show failed for {ref}:{path}: {result.stderr.strip()}")


def parse_version_from_json(json_text: str) -> str:
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise PluginVersionError(f"invalid JSON: {exc}") from exc
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise PluginVersionError("missing or empty 'version' field")
    return version


def _parse_semver(value: str) -> tuple[int, int, int]:
    match = SEMVER_RE.match(value)
    if not match:
        raise PluginVersionError(f"'{value}' is not a valid MAJOR.MINOR.PATCH version")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def compare_semver(old: str, new: str) -> bool:
    return _parse_semver(new) > _parse_semver(old)


def check_plugin(plugin_name: str, base_ref: str) -> CheckResult:
    manifest_path = PLUGIN_MANIFEST_TEMPLATE.format(name=plugin_name)

    head_json = read_version_json_at_ref(plugin_name, "HEAD")
    if head_json is None:
        if not plugin_dir_exists_at_ref(plugin_name, "HEAD"):
            return CheckResult(plugin_name, True, "plugin deleted in this PR — nothing to check")
        return CheckResult(
            plugin_name,
            False,
            f"{manifest_path} not found at HEAD — every plugin directory must have "
            "a manifest with a version",
        )

    try:
        head_version = parse_version_from_json(head_json)
    except PluginVersionError as exc:
        return CheckResult(plugin_name, False, f"invalid {manifest_path} at HEAD: {exc}")

    base_json = read_version_json_at_ref(plugin_name, base_ref)
    if base_json is None:
        return CheckResult(
            plugin_name, True, f"new plugin (no version at base) — HEAD version {head_version} OK"
        )

    try:
        base_version = parse_version_from_json(base_json)
    except PluginVersionError:
        return CheckResult(
            plugin_name,
            True,
            f"base {manifest_path} unparsable; treating as no prior version — HEAD {head_version} OK",
        )

    try:
        bumped = compare_semver(base_version, head_version)
    except PluginVersionError as exc:
        return CheckResult(plugin_name, False, f"invalid version comparison: {exc}")

    if not bumped:
        return CheckResult(
            plugin_name,
            False,
            f"version not bumped ({base_version} -> {head_version}); "
            f"bump {manifest_path}'s 'version' to greater than {base_version}",
        )
    return CheckResult(plugin_name, True, f"version bumped {base_version} -> {head_version}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Require a plugin's version to be bumped when its directory changes"
    )
    parser.add_argument("--base-ref", required=True, help="Git ref to diff against (e.g. origin/main)")
    args = parser.parse_args(argv)

    changed_files = get_changed_files(args.base_ref)
    touched_plugins = find_touched_plugins(changed_files)

    if not touched_plugins:
        print("No plugin directories touched; nothing to check.")
        return 0

    results = [check_plugin(name, args.base_ref) for name in sorted(touched_plugins)]

    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.plugin}: {result.message}")

    failures = [r for r in results if not r.ok]
    if failures:
        print(f"\n{len(failures)} plugin(s) failed the version check.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
