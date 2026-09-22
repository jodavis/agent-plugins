#!/usr/bin/env python3
"""Resolve a PR reference to exactly one owner/repo#number.

Usage:
    resolve_pr_reference.py "<ref>"
    resolve_pr_reference.py "<ref>" --jira-links '<json array of links, possibly empty>'

`<ref>` may be a full GitHub PR URL, a bare PR number (or `#123`), or a work-item ID.
Handles every deterministic resolution path itself: ref-shape classification, `gh pr view`
existence/access checks, the `use-context-file` context-file read, the GitHub-search fallback,
and the GitHub GraphQL linked-PR lookup (`getLinkedPullRequests`). The one Jira-specific step —
calling the `getJiraIssueRemoteIssueLinks` MCP operation — is not reachable from a script; the
`resolve-pr-reference` skill calls it itself and passes the result back in via `--jira-links`.

`main()` is a thin CLI wrapper: prints `resolve_pr_reference()`'s result as one JSON object to
stdout with exit 0, whether it resolved or reports a structured `not_found`/`ambiguous`/
`access_denied` failure. A hard failure of the script itself (e.g. malformed `--jira-links` JSON)
prints `Error: ...` to stderr and exits non-zero instead.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_WORKFLOW_ORCHESTRATE_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "workflow-orchestrate" / "scripts"
)
_MERGE_CONFIG_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "get-project-configuration" / "scripts"
)

sys.path.insert(0, str(_WORKFLOW_ORCHESTRATE_SCRIPTS_DIR))
sys.path.insert(0, str(_MERGE_CONFIG_SCRIPTS_DIR))

from dev_team import compute_context_path  # noqa: E402
from get_context_path import get_repo_slug  # noqa: E402
from pipeline_context import PipelineContext  # noqa: E402
from merge_config import YamlParseError, build_merged_config  # noqa: E402

_PR_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)$")
_BARE_NUMBER_RE = re.compile(r"^#?(\d+)$")

_LINKED_PRS_QUERY = (
    "query($owner: String!, $repo: String!, $number: Int!) {"
    " repository(owner: $owner, name: $repo) {"
    " issue(number: $number) {"
    " closedByPullRequestsReferences(first: 10) { nodes { number } } } } }"
)


# ---------------------------------------------------------------------------
# gh pr view — existence/access checks shared by the url and number paths
# ---------------------------------------------------------------------------

def _classify_gh_error(stderr: str) -> str:
    """Heuristic: a permission/authentication signal in gh's stderr is access_denied; anything
    else (not found, malformed reference, generic API error) is not_found. Wording of gh's own
    error text isn't a stable contract, so this only looks for common access-related keywords."""
    lowered = (stderr or "").lower()
    if "403" in lowered or "permission" in lowered or "access" in lowered or "authenticat" in lowered:
        return "access_denied"
    return "not_found"


def _resolve_pr(owner: str, repo: str, number: int, source: str) -> dict:
    pr_url = f"https://github.com/{owner}/{repo}/pull/{number}"
    result = subprocess.run(
        ["gh", "pr", "view", pr_url, "--json", "number,url,state"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        status = _classify_gh_error(result.stderr)
        return {"status": status, "detail": f"gh pr view failed for {pr_url}: {result.stderr.strip() or 'unknown error'}"}
    try:
        json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "not_found", "detail": f"gh pr view returned unexpected output for {pr_url}"}
    return {
        "status": "resolved",
        "owner": owner,
        "repo": repo,
        "number": number,
        "pr_url": pr_url,
        "source": source,
    }


# ---------------------------------------------------------------------------
# Repo-slug helpers
# ---------------------------------------------------------------------------

def _split_repo_slug(slug: str) -> tuple[str | None, str | None]:
    parts = slug.split("/")
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


def _resolve_bare_number(number: int) -> dict:
    owner, repo = _split_repo_slug(get_repo_slug())
    if owner is None:
        return {
            "status": "not_found",
            "detail": "could not parse owner/repo from the current repo's git remote 'origin' to resolve a bare PR number",
        }
    return _resolve_pr(owner, repo, number, source="number")


# ---------------------------------------------------------------------------
# Work-item-id pattern matching
# ---------------------------------------------------------------------------

def _match_work_item_provider(ref: str, work_tracking: dict) -> str | None:
    if not isinstance(work_tracking, dict):
        return None
    for provider_name, provider_config in work_tracking.items():
        if not isinstance(provider_config, dict):
            continue
        patterns = []
        issue_key_pattern = provider_config.get("issue-key-pattern")
        if issue_key_pattern:
            patterns.append(issue_key_pattern)
        patterns.extend(provider_config.get("recognize-patterns") or [])
        for pattern in patterns:
            try:
                if re.fullmatch(pattern, ref):
                    return provider_name
            except re.error:
                continue
    return None


def _context_file_pr_url(work_item_id: str, repo_slug: str) -> str | None:
    path = compute_context_path(work_item_id, repo_slug)
    if not path.exists():
        return None
    ctx = PipelineContext.load(path)
    return ctx.pr_url or None


def _finalize_matches(pr_refs: list[tuple[str, str, int]], source: str, ref: str) -> dict:
    unique = sorted(set(pr_refs))
    if not unique:
        return {"status": "not_found", "detail": f"no PR found for work item {ref!r} ({source} path)"}
    if len(unique) > 1:
        listed = ", ".join(f"{owner}/{repo}#{number}" for owner, repo, number in unique)
        return {"status": "ambiguous", "detail": f"multiple PRs linked to work item {ref!r}: {listed}"}
    owner, repo, number = unique[0]
    return {
        "status": "resolved",
        "owner": owner,
        "repo": repo,
        "number": number,
        "pr_url": f"https://github.com/{owner}/{repo}/pull/{number}",
        "source": source,
    }


# ---------------------------------------------------------------------------
# Jira work-item path: remote links, then GitHub-search fallback
# ---------------------------------------------------------------------------

def _jira_links_to_prs(jira_links: list) -> list[tuple[str, str, int]]:
    matches: list[tuple[str, str, int]] = []
    for link in jira_links or []:
        if not isinstance(link, dict):
            continue
        url = link.get("url")
        if not url:
            obj = link.get("object")
            if isinstance(obj, dict):
                url = obj.get("url")
        if not url:
            continue
        match = _PR_URL_RE.match(url)
        if match:
            matches.append((match.group(1), match.group(2), int(match.group(3))))
    return matches


def _github_search_fallback(owner: str, repo: str, issue_key: str) -> list[tuple[str, str, int]]:
    matches: set[tuple[str, str, int]] = set()

    search_result = subprocess.run(
        ["gh", "search", "prs", issue_key, "--repo", f"{owner}/{repo}", "--json", "number,url"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if search_result.returncode == 0:
        try:
            for item in json.loads(search_result.stdout):
                number = item.get("number")
                if number is not None:
                    matches.add((owner, repo, int(number)))
        except json.JSONDecodeError:
            pass

    list_result = subprocess.run(
        ["gh", "pr", "list", "--repo", f"{owner}/{repo}", "--state", "all", "--json", "number,headRefName"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if list_result.returncode == 0:
        try:
            for item in json.loads(list_result.stdout):
                head_ref = item.get("headRefName") or ""
                if issue_key in head_ref:
                    number = item.get("number")
                    if number is not None:
                        matches.add((owner, repo, int(number)))
        except json.JSONDecodeError:
            pass

    return list(matches)


def _resolve_jira_work_item(ref: str, owner: str, repo: str, jira_links: list) -> dict:
    pr_refs = _jira_links_to_prs(jira_links)
    if pr_refs:
        return _finalize_matches(pr_refs, source="work-item-jira-remote-link", ref=ref)
    pr_refs = _github_search_fallback(owner, repo, ref)
    return _finalize_matches(pr_refs, source="work-item-jira-github-search", ref=ref)


# ---------------------------------------------------------------------------
# GitHub work-item path: getLinkedPullRequests (gh api graphql)
# ---------------------------------------------------------------------------

def _github_linked_prs(owner: str, repo: str, issue_number: int) -> list[tuple[str, str, int]]:
    result = subprocess.run(
        [
            "gh", "api", "graphql",
            "-f", f"query={_LINKED_PRS_QUERY}",
            "-F", f"owner={owner}",
            "-F", f"repo={repo}",
            "-F", f"number={issue_number}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    nodes = (
        (data.get("data") or {}).get("repository") or {}
    ).get("issue") or {}
    nodes = (nodes.get("closedByPullRequestsReferences") or {}).get("nodes") or []
    matches: list[tuple[str, str, int]] = []
    for node in nodes:
        number = node.get("number")
        if number is not None:
            matches.append((owner, repo, int(number)))
    return matches


def _resolve_github_work_item(ref: str, owner: str, repo: str) -> dict:
    number_match = re.search(r"\d+", ref)
    if not number_match:
        return {
            "status": "not_found",
            "detail": f"could not extract a numeric issue number from GitHub work-item ref {ref!r}",
        }
    issue_number = int(number_match.group())
    pr_refs = _github_linked_prs(owner, repo, issue_number)
    return _finalize_matches(pr_refs, source="work-item-github-linked-pr", ref=ref)


# ---------------------------------------------------------------------------
# Work-item dispatch: context file first, then provider-specific resolution
# ---------------------------------------------------------------------------

def _resolve_work_item(ref: str, provider: str, jira_links: list) -> dict:
    repo_slug = get_repo_slug()

    context_pr_url = _context_file_pr_url(ref, repo_slug)
    if context_pr_url:
        match = _PR_URL_RE.match(context_pr_url)
        if not match:
            return {
                "status": "not_found",
                "detail": f"context file for work item {ref!r} has a pr_url that does not match the expected GitHub PR URL format: {context_pr_url!r}",
            }
        owner, repo, number = match.group(1), match.group(2), int(match.group(3))
        return {
            "status": "resolved",
            "owner": owner,
            "repo": repo,
            "number": number,
            "pr_url": context_pr_url,
            "source": "work-item-context-file",
        }

    owner, repo = _split_repo_slug(repo_slug)
    if owner is None:
        return {
            "status": "not_found",
            "detail": f"could not parse owner/repo from the current repo's git remote 'origin' to resolve work item {ref!r}",
        }

    if provider == "jira":
        return _resolve_jira_work_item(ref, owner, repo, jira_links)
    if provider == "github":
        return _resolve_github_work_item(ref, owner, repo)
    return {
        "status": "not_found",
        "detail": f"ref {ref!r} matched provider {provider!r}'s work-item-id pattern, but no resolution logic is implemented for that provider",
    }


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def resolve_pr_reference(ref: str, jira_links: list | None = None) -> dict:
    ref = (ref or "").strip()
    if not ref:
        return {"status": "not_found", "detail": "ref is empty; did not match any recognized format"}

    url_match = _PR_URL_RE.match(ref)
    if url_match:
        owner, repo, number = url_match.group(1), url_match.group(2), int(url_match.group(3))
        return _resolve_pr(owner, repo, number, source="url")

    bare_match = _BARE_NUMBER_RE.match(ref)
    if bare_match:
        return _resolve_bare_number(int(bare_match.group(1)))

    try:
        config = build_merged_config()
    except (YamlParseError, RuntimeError) as e:
        return {
            "status": "not_found",
            "detail": f"ref {ref!r} did not match any recognized format, and project configuration could not be loaded to check work-item-id patterns: {e}",
        }

    provider = _match_work_item_provider(ref, config.get("work-tracking") or {})
    if provider is None:
        return {
            "status": "not_found",
            "detail": (
                f"ref {ref!r} did not match any recognized format: not a bare number, '#123', "
                "full GitHub PR URL, or a work-item-id pattern configured for any provider"
            ),
        }

    return _resolve_work_item(ref, provider, jira_links or [])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ref")
    parser.add_argument("--jira-links", default=None)
    args = parser.parse_args()

    jira_links = None
    if args.jira_links is not None:
        try:
            jira_links = json.loads(args.jira_links)
        except json.JSONDecodeError as e:
            print(f"Error: --jira-links is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)

    result = resolve_pr_reference(args.ref, jira_links=jira_links)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
