"""Tests for pr_from_context.py — should_submit_via_stack (the step-4 stack-vs-create-pr branch
decision) and resolve_submitted_pr_url (the stack-submit PR-URL lookup, which must raise instead
of silently resolving to `null` when `gh pr list` finds no match).
"""

import json

import pytest

from pr_from_context import StackPrLookupError, resolve_submitted_pr_url, should_submit_via_stack


# ---------------------------------------------------------------------------
# should_submit_via_stack — case-insensitively "true" submits via stack;
# everything else, including empty/absent, falls back to create-pr
# ---------------------------------------------------------------------------

class TestShouldSubmitViaStack:
    @pytest.mark.parametrize(
        "added_to_stack, expected",
        [
            pytest.param("true", True, id="lowercase_true"),
            pytest.param("True", True, id="titlecase_true"),
            pytest.param("TRUE", True, id="uppercase_true"),
            pytest.param("  true  ", True, id="true_with_surrounding_whitespace"),
            pytest.param("false", False, id="lowercase_false"),
            pytest.param("", False, id="empty_string"),
            pytest.param("garbage", False, id="unrecognized_value"),
        ],
    )
    def test_should_submit_via_stack_matches_pipeline_context_parsing_convention(
        self, added_to_stack, expected
    ):
        # Act
        result = should_submit_via_stack(added_to_stack)

        # Assert
        assert result is expected


# ---------------------------------------------------------------------------
# resolve_submitted_pr_url — a single matching entry resolves to its url
# ---------------------------------------------------------------------------

class TestResolveSubmittedPrUrlSingleMatch:
    def test_resolve_submitted_pr_url_single_entry_returns_its_url(self):
        # Arrange
        pr_list_json = json.dumps([{"url": "https://github.com/acme/widget/pull/57"}])

        # Act
        result = resolve_submitted_pr_url(pr_list_json)

        # Assert
        assert result == "https://github.com/acme/widget/pull/57"


# ---------------------------------------------------------------------------
# resolve_submitted_pr_url — an empty result (submit succeeded but the PR
# isn't visible yet, or the head-branch name didn't match) raises rather
# than silently resolving to null
# ---------------------------------------------------------------------------

class TestResolveSubmittedPrUrlNoMatch:
    def test_resolve_submitted_pr_url_empty_list_raises_stack_pr_lookup_error(self):
        # Act / Assert
        with pytest.raises(StackPrLookupError):
            resolve_submitted_pr_url(json.dumps([]))


# ---------------------------------------------------------------------------
# resolve_submitted_pr_url — malformed JSON raises the same error type
# rather than propagating a raw JSONDecodeError
# ---------------------------------------------------------------------------

class TestResolveSubmittedPrUrlMalformedJson:
    def test_resolve_submitted_pr_url_malformed_json_raises_stack_pr_lookup_error(self):
        # Act / Assert
        with pytest.raises(StackPrLookupError):
            resolve_submitted_pr_url("not json")


# ---------------------------------------------------------------------------
# resolve_submitted_pr_url — multiple matching entries take the first, same
# as the `jq '.[0].url'` convention it replaces
# ---------------------------------------------------------------------------

class TestResolveSubmittedPrUrlMultipleMatches:
    def test_resolve_submitted_pr_url_multiple_entries_returns_first(self):
        # Arrange
        pr_list_json = json.dumps(
            [
                {"url": "https://github.com/acme/widget/pull/57"},
                {"url": "https://github.com/acme/widget/pull/58"},
            ]
        )

        # Act
        result = resolve_submitted_pr_url(pr_list_json)

        # Assert
        assert result == "https://github.com/acme/widget/pull/57"
