"""Tests for tdd_cycle.py.

Covers:
- classify_reply() — parsing the trio's one-line status markers
- is_test_file() — the file-scope heuristic
- TrioState — save/load round-trip
- git helpers (changed_files/stage/discard_unstaged/commit) against real tmp_path repos
- run_cycle() — the full state machine, driven with a scripted fake `send_turn` so no
  real `claude` CLI invocation is needed

NOTE: nothing here exercises the real `run_claude_turn()` subprocess call — that's the
one unverified boundary (see tdd_cycle.py's module docstring); it needs a live `claude`
invocation to confirm, which wasn't available while writing this.
"""

from pathlib import Path

import pytest

from tdd_cycle import (
    DoneResult,
    EscalationResult,
    TddProtocolError,
    TrioState,
    changed_files,
    classify_reply,
    commit,
    discard_unstaged,
    is_test_file,
    run_cycle,
    stage,
)


def _repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)
    return root


# ---------------------------------------------------------------------------
# classify_reply
# ---------------------------------------------------------------------------

class TestClassifyReply:
    def test_structural_red(self):
        kind, details = classify_reply("structural-red: test_foo — build fails")
        assert kind == "structural_red"
        assert details["detail"] == "test_foo — build fails"

    def test_red(self):
        kind, details = classify_reply("red: test_foo — assertion fails")
        assert kind == "red"
        assert details["detail"] == "test_foo — assertion fails"

    def test_done(self):
        kind, details = classify_reply("done: all branches covered")
        assert kind == "done"
        assert details["detail"] == "all branches covered"

    def test_structural_green(self):
        kind, details = classify_reply("structural-green: test_foo")
        assert kind == "structural_green"
        assert details["detail"] == "test_foo"

    def test_green(self):
        kind, details = classify_reply("green: test_foo")
        assert kind == "green"
        assert details["detail"] == "test_foo"

    def test_revise_request(self):
        kind, details = classify_reply("revise-request: test_foo — assert looks wrong")
        assert kind == "revise_request"
        assert details["detail"] == "test_foo — assert looks wrong"

    def test_escalate_parses_reason_and_recommended_action(self):
        kind, details = classify_reply(
            "escalate: ambiguous requirement — recommended_action: clarify"
        )
        assert kind == "escalate"
        assert details["reason"] == "ambiguous requirement"
        assert details["recommended_action"] == "clarify"

    def test_refactored(self):
        kind, details = classify_reply("refactored: consolidated two tests")
        assert kind == "refactored"
        assert details["detail"] == "consolidated two tests"

    def test_no_refactor_needed(self):
        kind, _details = classify_reply("no-refactor-needed")
        assert kind == "no_refactor_needed"

    def test_marker_on_first_line_with_explanation_following(self):
        text = "green: test_foo\n\nI implemented the minimal change to satisfy the assertion."
        kind, details = classify_reply(text)
        assert kind == "green"
        assert details["detail"] == "test_foo"

    def test_leading_blank_lines_skipped(self):
        kind, _details = classify_reply("\n\ndone: coverage complete")
        assert kind == "done"

    def test_marker_found_after_leading_prose_and_inside_a_code_fence(self):
        # Real observed case: a trio member led with an explanatory sentence, then
        # wrapped the actual one-liner in a ``` fence further down.
        text = (
            "Fails for the right reason: round-trip mismatch.\n\n"
            "```\n"
            "red: test_foo — assertion fails\n"
            "```"
        )
        kind, details = classify_reply(text)
        assert kind == "red"
        assert details["detail"] == "test_foo — assertion fails"

    def test_unrecognized_text_returns_unrecognized(self):
        kind, details = classify_reply("I'm not sure what to do here.")
        assert kind == "unrecognized"
        assert details["raw"] == "I'm not sure what to do here."

    def test_empty_text_returns_unrecognized_with_empty_raw(self):
        kind, details = classify_reply("")
        assert kind == "unrecognized"
        assert details["raw"] == ""


# ---------------------------------------------------------------------------
# is_test_file
# ---------------------------------------------------------------------------

class TestIsTestFile:
    def test_test_prefix_recognized(self):
        assert is_test_file("plugins/dev-team/scripts/test_pipeline_context.py") is True

    def test_test_suffix_recognized(self):
        assert is_test_file("src/pipeline_context_test.py") is True

    def test_production_file_not_recognized(self):
        assert is_test_file("plugins/dev-team/scripts/pipeline_context.py") is False

    def test_file_containing_but_not_starting_with_test_not_recognized(self):
        assert is_test_file("plugins/dev-team/scripts/latest_context.py") is False


# ---------------------------------------------------------------------------
# TrioState
# ---------------------------------------------------------------------------

class TestTrioState:
    def test_missing_file_returns_fresh_state(self, tmp_path):
        state = TrioState.load(tmp_path / "does-not-exist.json")
        assert state.tester_session is None
        assert state.implementer_session is None
        assert state.refactorer_session is None

    def test_roundtrip_through_save_load(self, tmp_path):
        path = tmp_path / "state.json"
        state = TrioState(
            tester_session="t1", implementer_session="i1", refactorer_session="r1",
            last_tester_reply="red: test_foo",
        )
        state.save(path)
        loaded = TrioState.load(path)
        assert loaded == state

    def test_save_creates_parent_directories(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "state.json"
        TrioState().save(path)
        assert path.exists()


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------

class TestGitHelpers:
    def test_changed_files_lists_modified_paths(self, tmp_path):
        root = _repo_root(tmp_path)
        (root / "test_foo.py").write_text("x", encoding="utf-8")
        assert changed_files(root) == ["test_foo.py"]

    def test_changed_files_empty_when_clean(self, tmp_path):
        root = _repo_root(tmp_path)
        assert changed_files(root) == []

    def test_stage_adds_given_paths(self, tmp_path):
        import subprocess

        root = _repo_root(tmp_path)
        (root / "test_foo.py").write_text("x", encoding="utf-8")
        stage(root, ["test_foo.py"])
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], cwd=root, capture_output=True, text=True,
        )
        assert result.stdout.strip() == "test_foo.py"

    def test_stage_with_empty_list_is_a_no_op(self, tmp_path):
        root = _repo_root(tmp_path)
        stage(root, [])  # must not raise on an empty git add invocation

    def test_discard_unstaged_reverts_working_tree_change(self, tmp_path):
        root = _repo_root(tmp_path)
        (root / "README.md").write_text("mutated", encoding="utf-8")
        discard_unstaged(root, ["README.md"])
        assert (root / "README.md").read_text(encoding="utf-8") == "x"

    def test_commit_creates_commit_with_expected_message_format(self, tmp_path):
        import subprocess

        root = _repo_root(tmp_path)
        (root / "pipeline_context.py").write_text("x", encoding="utf-8")
        message = commit(root, "ADR-335", "PipelineContext", "12 behaviors covered")
        assert message == "ADR-335: implement PipelineContext via TDD (12 behaviors covered)"
        log = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"], cwd=root, capture_output=True, text=True,
        )
        assert log.stdout.strip() == message


# ---------------------------------------------------------------------------
# run_cycle — the full state machine, driven by a scripted fake send_turn
# ---------------------------------------------------------------------------

def _make_fake_send_turn(script):
    """`script` is a list of dicts: {"reply": str, "mutate": callable(repo_root) | None}.
    Each call consumes the next entry in order; raises IndexError if the state machine
    calls more turns than scripted (surfaces as a clear test failure)."""
    calls = []
    remaining = list(script)

    def _fake(*, message, agent, session_id, repo_root, permission_mode="acceptEdits"):
        calls.append({"message": message, "agent": agent, "session_id": session_id})
        entry = remaining.pop(0)
        if entry.get("mutate"):
            entry["mutate"](repo_root)
        new_session_id = session_id or f"session-{len(calls)}"
        return new_session_id, entry["reply"]

    _fake.calls = calls
    return _fake


def _write_test_file(name="test_foo.py", content="x"):
    return lambda root: (root / name).write_text(content, encoding="utf-8")


def _write_production_file(name="foo.py", content="x"):
    return lambda root: (root / name).write_text(content, encoding="utf-8")


class TestRunCycleHappyPath:
    def test_single_behavior_reaches_done_and_commits(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        send_turn = _make_fake_send_turn([
            {"reply": "red: test_foo — assertion fails", "mutate": _write_test_file()},
            {"reply": "green: test_foo", "mutate": _write_production_file()},
            {"reply": "no-refactor-needed"},
            {"reply": "done: 1 behavior covered"},
        ])

        result = run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=TrioState(), state_path=state_path, send_turn=send_turn,
        )

        assert isinstance(result, DoneResult)
        assert result.coverage_summary == "1 behavior covered"
        assert result.commit_message == "ADR-1: implement Widget via TDD (1 behavior covered)"

    def test_first_turn_to_each_role_includes_component_prompt(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        send_turn = _make_fake_send_turn([
            {"reply": "red: test_foo — assertion fails", "mutate": _write_test_file()},
            {"reply": "green: test_foo", "mutate": _write_production_file()},
            {"reply": "no-refactor-needed"},
            {"reply": "done: 1 behavior covered"},
        ])

        run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=TrioState(), state_path=state_path, send_turn=send_turn,
        )

        first_tester_call, first_implementer_call, first_refactorer_call = send_turn.calls[0:3]
        assert "Build a Widget." in first_tester_call["message"]
        assert first_tester_call["agent"] == "dev-team:tdd-tester"
        assert "Build a Widget." in first_implementer_call["message"]
        assert first_implementer_call["agent"] == "dev-team:tdd-implementer"
        assert "Build a Widget." in first_refactorer_call["message"]
        assert first_refactorer_call["agent"] == "dev-team:tdd-refactorer"

    def test_later_turns_omit_component_prompt_and_agent(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        send_turn = _make_fake_send_turn([
            {"reply": "red: test_foo — assertion fails", "mutate": _write_test_file()},
            {"reply": "green: test_foo", "mutate": _write_production_file()},
            {"reply": "no-refactor-needed"},
            {"reply": "red: test_bar — assertion fails", "mutate": _write_test_file("test_bar.py")},
            {"reply": "green: test_bar"},
            {"reply": "no-refactor-needed"},
            {"reply": "done: 2 behaviors covered"},
        ])

        run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=TrioState(), state_path=state_path, send_turn=send_turn,
        )

        second_tester_call = send_turn.calls[3]
        assert "Build a Widget." not in second_tester_call["message"]
        assert second_tester_call["agent"] is None
        assert second_tester_call["session_id"] == "session-1"

    def test_structural_turn_routes_back_to_tester_without_refactor(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        send_turn = _make_fake_send_turn([
            {"reply": "structural-red: test_foo — build fails", "mutate": _write_test_file()},
            {"reply": "structural-green: test_foo", "mutate": _write_production_file()},
            {"reply": "red: test_foo — assertion fails", "mutate": _write_test_file(content="y")},
            {"reply": "green: test_foo"},
            {"reply": "no-refactor-needed"},
            {"reply": "done: 1 behavior covered"},
        ])

        result = run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=TrioState(), state_path=state_path, send_turn=send_turn,
        )

        assert isinstance(result, DoneResult)
        # Only one refactor turn (agent dev-team:tdd-refactorer) should have been called —
        # the structural-green did not trigger one.
        refactorer_calls = [c for c in send_turn.calls if c["agent"] == "dev-team:tdd-refactorer"]
        assert len(refactorer_calls) == 1

    def test_revise_request_tier_1_retry_succeeds(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        send_turn = _make_fake_send_turn([
            {"reply": "red: test_foo — assertion fails", "mutate": _write_test_file()},
            {"reply": "revise-request: test_foo — assert looks wrong"},
            {"reply": "red: test_foo — clarified assertion"},
            {"reply": "green: test_foo", "mutate": _write_production_file()},
            {"reply": "no-refactor-needed"},
            {"reply": "done: 1 behavior covered"},
        ])

        result = run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=TrioState(), state_path=state_path, send_turn=send_turn,
        )

        assert isinstance(result, DoneResult)


class TestRunCycleEscalationsAndViolations:
    def test_escalate_returns_escalation_result_with_recommended_action(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        send_turn = _make_fake_send_turn([
            {"reply": "red: test_foo — assertion fails", "mutate": _write_test_file()},
            {"reply": "escalate: ambiguous requirement — recommended_action: clarify"},
        ])

        result = run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=TrioState(), state_path=state_path, send_turn=send_turn,
        )

        assert isinstance(result, EscalationResult)
        assert result.recommended_action == "clarify"
        assert result.reason == "ambiguous requirement"
        assert Path(result.state_file).exists()

    def test_second_revise_request_after_retry_escalates_as_protocol_violation(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        send_turn = _make_fake_send_turn([
            {"reply": "red: test_foo — assertion fails", "mutate": _write_test_file()},
            {"reply": "revise-request: test_foo — assert looks wrong"},
            {"reply": "red: test_foo — same issue"},
            {"reply": "revise-request: test_foo — still wrong"},
        ])

        result = run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=TrioState(), state_path=state_path, send_turn=send_turn,
        )

        assert isinstance(result, EscalationResult)
        assert result.recommended_action == "protocol_violation"

    def test_tester_touching_production_file_is_a_protocol_violation_and_reverted(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        send_turn = _make_fake_send_turn([
            {"reply": "red: test_foo — assertion fails", "mutate": _write_production_file("sneaky.py")},
        ])

        result = run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=TrioState(), state_path=state_path, send_turn=send_turn,
        )

        assert isinstance(result, EscalationResult)
        assert result.recommended_action == "protocol_violation"
        assert not (root / "sneaky.py").exists()

    def test_implementer_touching_test_file_is_a_protocol_violation_and_reverted(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        send_turn = _make_fake_send_turn([
            {"reply": "red: test_foo — assertion fails", "mutate": _write_test_file()},
            {"reply": "green: test_foo", "mutate": _write_test_file("test_sneaky.py")},
        ])

        result = run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=TrioState(), state_path=state_path, send_turn=send_turn,
        )

        assert isinstance(result, EscalationResult)
        assert result.recommended_action == "protocol_violation"
        assert not (root / "test_sneaky.py").exists()

    def test_unrecognized_tester_reply_is_a_protocol_violation(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        send_turn = _make_fake_send_turn([{"reply": "uh, not sure?"}])

        result = run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=TrioState(), state_path=state_path, send_turn=send_turn,
        )

        assert isinstance(result, EscalationResult)
        assert result.recommended_action == "protocol_violation"

    def test_exceeding_max_turns_raises(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        # tester/implementer alternate structural-red/structural-green forever — a
        # structural turn never produces a real green, so the loop never converges.
        cycle = [
            {"reply": "structural-red: test_foo — build fails", "mutate": _write_test_file()},
            {"reply": "structural-green: test_foo", "mutate": _write_production_file()},
        ]
        send_turn = _make_fake_send_turn(cycle * 5)

        with pytest.raises(TddProtocolError):
            run_cycle(
                component="Widget", component_prompt="Build a Widget.", repo_root=root,
                work_item_id="ADR-1", state=TrioState(), state_path=state_path,
                send_turn=send_turn, max_turns=3,
            )


class TestRunCycleResumption:
    def test_injected_answer_resends_implementer_with_folded_in_answer(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        state = TrioState(
            tester_session="t1", implementer_session="i1", refactorer_session="r1",
            last_tester_reply="red: test_foo — assertion fails",
        )
        send_turn = _make_fake_send_turn([
            {"reply": "green: test_foo", "mutate": _write_production_file()},
            {"reply": "no-refactor-needed"},
            {"reply": "done: 1 behavior covered"},
        ])

        result = run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=state, state_path=state_path,
            injected_answer="use option B", send_turn=send_turn,
        )

        assert isinstance(result, DoneResult)
        first_call = send_turn.calls[0]
        assert first_call["session_id"] == "i1"
        assert "red: test_foo — assertion fails" in first_call["message"]
        assert "use option B" in first_call["message"]

    def test_resolved_directly_skips_straight_to_refactor_turn(self, tmp_path):
        root = _repo_root(tmp_path)
        state_path = tmp_path / "state.json"
        state = TrioState(
            tester_session="t1", implementer_session="i1", refactorer_session="r1",
        )
        (root / "resolved.py").write_text("x", encoding="utf-8")
        send_turn = _make_fake_send_turn([
            {"reply": "no-refactor-needed"},
            {"reply": "done: 1 behavior covered"},
        ])

        result = run_cycle(
            component="Widget", component_prompt="Build a Widget.", repo_root=root,
            work_item_id="ADR-1", state=state, state_path=state_path,
            resolved_directly=True, send_turn=send_turn,
        )

        assert isinstance(result, DoneResult)
        first_call = send_turn.calls[0]
        assert first_call["agent"] is None
        assert first_call["session_id"] == "r1"
