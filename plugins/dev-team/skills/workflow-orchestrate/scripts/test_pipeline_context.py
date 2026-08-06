"""Tests for pipeline_context.py — the PipelineContext dataclass and its
save()/load() persistence to/from a markdown file with YAML-ish frontmatter
plus named '<!-- section:Name -->' body sections.

Covers:
- Known frontmatter field defaults and save/load round-trips
- extra_frontmatter preservation for unrecognized frontmatter keys
- Known body sections, written only when non-empty and read back by load()
- The new 'Project Configuration' section (first section, before Workspace Setup)
- Logs section write-only behavior
- started/last_updated parse-failure fallback
- _parse_frontmatter / _parse_sections standalone helper behaviors
"""

import datetime
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# PipelineContext construction defaults
# ---------------------------------------------------------------------------

class TestPipelineContextDefaults:
    def make_sut(self, **kwargs):
        from pipeline_context import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_construction_with_only_work_item_id_uses_defaults_for_all_other_fields(self):
        ctx = self.make_sut()

        assert ctx.work_item_id == "ADR-TEST"
        assert ctx.spec_path == ""
        assert ctx.state == "init"
        assert ctx.fix_iteration == 0
        assert ctx.review_fix_iteration == 0
        assert ctx.pr_url == ""
        assert ctx.build_log == ""
        assert ctx.test_log == ""
        assert ctx.signoff_cycle_count == 0
        assert ctx.consecutive_failures == 0
        assert ctx.review_cycle_count == 0
        assert ctx.troubleshooter_input == ""
        assert ctx.pending_agent == ""
        assert ctx.added_to_stack is False
        assert ctx.project_configuration == ""
        assert isinstance(ctx.started, datetime.datetime)
        assert isinstance(ctx.last_updated, datetime.datetime)


# ---------------------------------------------------------------------------
# save() / load() round trip for known frontmatter fields
# ---------------------------------------------------------------------------

class TestPipelineContextSaveLoadRoundTrip:
    def make_sut(self, **kwargs):
        from pipeline_context import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_save_then_load_roundtrips_all_known_scalar_frontmatter_fields(self, tmp_path):
        # Arrange
        from pipeline_context import PipelineContext
        ctx = self.make_sut(
            spec_path="_spec_Foo.md",
            state="researching",
            fix_iteration=2,
            review_fix_iteration=1,
            pr_url="https://github.com/example/pr/1",
            build_log="build.log",
            test_log="test.log",
            signoff_cycle_count=3,
            consecutive_failures=1,
            review_cycle_count=4,
            troubleshooter_input="some input",
            pending_agent="researcher",
            added_to_stack=True,
        )
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)
        loaded = PipelineContext.load(path)

        # Assert
        assert loaded.work_item_id == "ADR-TEST"
        assert loaded.spec_path == "_spec_Foo.md"
        assert loaded.state == "researching"
        assert loaded.fix_iteration == 2
        assert loaded.review_fix_iteration == 1
        assert loaded.pr_url == "https://github.com/example/pr/1"
        assert loaded.build_log == "build.log"
        assert loaded.test_log == "test.log"
        assert loaded.signoff_cycle_count == 3
        assert loaded.consecutive_failures == 1
        assert loaded.review_cycle_count == 4
        assert loaded.troubleshooter_input == "some input"
        assert loaded.pending_agent == "researcher"
        assert loaded.added_to_stack is True

    def test_save_then_load_roundtrips_started_and_last_updated_timestamps(self, tmp_path):
        # Arrange
        from pipeline_context import PipelineContext
        ctx = self.make_sut()
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)
        loaded = PipelineContext.load(path)

        # Assert
        assert loaded.started == ctx.started
        assert loaded.last_updated == ctx.last_updated

    def test_save_then_load_roundtrips_default_empty_string_scalar_frontmatter_fields(self, tmp_path):
        # Arrange
        from pipeline_context import PipelineContext
        ctx = self.make_sut()
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)
        loaded = PipelineContext.load(path)

        # Assert
        assert loaded.spec_path == ""
        assert loaded.pr_url == ""
        assert loaded.build_log == ""
        assert loaded.test_log == ""
        assert loaded.troubleshooter_input == ""
        assert loaded.pending_agent == ""


# ---------------------------------------------------------------------------
# save() side effects: parent directory creation, last_updated bump, heading
# ---------------------------------------------------------------------------

class TestPipelineContextSaveCreatesParentDirectory:
    def make_sut(self, **kwargs):
        from pipeline_context import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_save_to_path_with_missing_parent_directory_creates_it_and_writes_file(self, tmp_path):
        # Arrange
        ctx = self.make_sut()
        path = tmp_path / "nested" / "subdir" / "ctx.md"

        # Act
        ctx.save(path)

        # Assert
        assert path.exists()


class TestPipelineContextSaveBumpsLastUpdated:
    def make_sut(self, **kwargs):
        from pipeline_context import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_save_updates_last_updated_to_current_time_on_each_call(self, tmp_path):
        # Arrange
        ctx = self.make_sut()
        original_last_updated = ctx.last_updated
        path = tmp_path / "ctx.md"
        time.sleep(0.01)

        # Act
        ctx.save(path)

        # Assert
        assert ctx.last_updated > original_last_updated


class TestPipelineContextSaveWritesHeading:
    def make_sut(self, **kwargs):
        from pipeline_context import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_save_writes_work_item_id_heading_after_frontmatter(self, tmp_path):
        # Arrange
        ctx = self.make_sut()
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)

        # Assert
        text = path.read_text(encoding="utf-8")
        assert "# ADR-TEST Dev Team Context" in text


# ---------------------------------------------------------------------------
# added_to_stack — a proper named field (ADR-375), not routed through
# extra_frontmatter, with a default-false round trip
# ---------------------------------------------------------------------------

class TestPipelineContextAddedToStack:
    def make_sut(self, **kwargs):
        from pipeline_context import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_save_then_load_roundtrips_default_false_added_to_stack(self, tmp_path):
        # Arrange
        from pipeline_context import PipelineContext
        ctx = self.make_sut()
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)
        loaded = PipelineContext.load(path)

        # Assert
        assert loaded.added_to_stack is False

    def test_added_to_stack_true_survives_save_load_roundtrip_and_is_not_in_extra_frontmatter(self, tmp_path):
        # Arrange
        from pipeline_context import PipelineContext
        ctx = self.make_sut(added_to_stack=True)
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)
        loaded = PipelineContext.load(path)

        # Assert
        assert loaded.added_to_stack is True
        assert "added_to_stack" not in loaded.extra_frontmatter


# ---------------------------------------------------------------------------
# extra_frontmatter preservation for unrecognized frontmatter keys
# ---------------------------------------------------------------------------

class TestPipelineContextExtraFrontmatter:
    def make_sut(self, **kwargs):
        from pipeline_context import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_prepopulated_extra_frontmatter_field_survives_save_load_roundtrip(self, tmp_path):
        # Arrange
        from pipeline_context import PipelineContext
        ctx = self.make_sut(extra_frontmatter={"base_branch": "main"})
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)
        loaded = PipelineContext.load(path)

        # Assert
        assert loaded.extra_frontmatter["base_branch"] == "main"

    def _inject_frontmatter_line(self, path: Path, line: str) -> None:
        """Insert a raw line into the frontmatter block, just before the closing '---'."""
        lines = path.read_text(encoding="utf-8").split("\n")
        closing_idx = lines.index("---", 1)
        lines.insert(closing_idx, line)
        path.write_text("\n".join(lines), encoding="utf-8")

    @pytest.mark.parametrize(
        "injected_line",
        [
            pytest.param("working_branch: feature/ADR-335-foo", id="unknown_scalar_field"),
            pytest.param("extra_list:\n- alpha\n- beta", id="unknown_list_valued_field"),
        ],
    )
    def test_unknown_field_written_directly_survives_load_save_roundtrip(self, tmp_path, injected_line):
        # Arrange: simulate a frontmatter key PipelineContext doesn't declare as a
        # named field, written directly (e.g. via Edit) rather than through save().
        # Covers both a plain scalar value and a multi-line YAML list ('- item') value.
        from pipeline_context import PipelineContext
        ctx = self.make_sut()
        path = tmp_path / "ctx.md"
        ctx.save(path)
        self._inject_frontmatter_line(path, injected_line)

        # Act
        loaded = PipelineContext.load(path)
        loaded.save(path)

        # Assert
        resaved_text = path.read_text(encoding="utf-8")
        assert injected_line in resaved_text


# ---------------------------------------------------------------------------
# Known body sections, written only when non-empty and read back by load()
# ---------------------------------------------------------------------------

class TestPipelineContextBodySections:
    def make_sut(self, **kwargs):
        from pipeline_context import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    @pytest.mark.parametrize(
        "field_name, value",
        [
            pytest.param("workspace_setup", "Cloned repo to /tmp/workspace", id="workspace_setup"),
            pytest.param("debug_report", "Root cause: stale cache", id="debug_report"),
            pytest.param("brief", "Implement the frobnicator using the widget API.", id="brief"),
            pytest.param("project_configuration", "work_tracking: jira", id="project_configuration"),
            pytest.param("review_notes", "Please rename this variable.", id="review_notes"),
            pytest.param("last_failure", "Build failed: missing dependency.", id="last_failure"),
            pytest.param("signoff_review", "Looks good, approved.", id="signoff_review"),
            pytest.param("signoff_research", "Checked prior signoff cycles for regressions.", id="signoff_research"),
            pytest.param("signoff_build_result", "Build passed on signoff attempt 2.", id="signoff_build_result"),
            pytest.param("validate_result", "All exit criteria satisfied.", id="validate_result"),
            pytest.param("handoff_result", "Handed off to human reviewer.", id="handoff_result"),
        ],
    )
    def test_save_then_load_roundtrips_body_section(self, tmp_path, field_name, value):
        # Arrange
        from pipeline_context import PipelineContext
        ctx = self.make_sut(**{field_name: value})
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)
        loaded = PipelineContext.load(path)

        # Assert
        assert getattr(loaded, field_name) == value

    @pytest.mark.parametrize(
        "work_summaries",
        [
            pytest.param(["Added feature X"], id="single_work_summary_as_implementation_summary_section"),
            pytest.param(
                ["Added feature X", "Fixed edge case A", "Fixed edge case B"],
                id="additional_work_summaries_as_numbered_fix_sections",
            ),
        ],
    )
    def test_save_then_load_roundtrips_work_summaries(self, tmp_path, work_summaries):
        # Arrange
        from pipeline_context import PipelineContext
        ctx = self.make_sut(work_summaries=work_summaries)
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)
        loaded = PipelineContext.load(path)

        # Assert
        assert loaded.work_summaries == work_summaries


# ---------------------------------------------------------------------------
# Logs section: write-only, built from build_log/test_log, never read by load()
# ---------------------------------------------------------------------------

class TestPipelineContextLogsSection:
    def make_sut(self, **kwargs):
        from pipeline_context import PipelineContext
        return PipelineContext(work_item_id="ADR-TEST", **kwargs)

    def test_save_writes_logs_section_with_build_and_test_log_bullets(self, tmp_path):
        # Arrange
        ctx = self.make_sut(build_log="logs/build.txt", test_log="logs/test.txt")
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)

        # Assert
        text = path.read_text(encoding="utf-8")
        assert "<!-- section:Logs -->" in text
        assert "- Build: logs/build.txt" in text
        assert "- Tests: logs/test.txt" in text


# ---------------------------------------------------------------------------
# started/last_updated parse-failure fallback
# ---------------------------------------------------------------------------

class TestPipelineContextTimestampParseFailure:
    @pytest.mark.parametrize(
        "frontmatter_lines",
        [
            pytest.param(
                "work_item_id: ADR-TEST\nlast_updated: 2024-01-01T00:00:00\n",
                id="started_key_missing",
            ),
            pytest.param(
                "work_item_id: ADR-TEST\nstarted: not-a-real-timestamp\nlast_updated: 2024-01-01T00:00:00\n",
                id="started_value_malformed",
            ),
        ],
    )
    def test_load_falls_back_to_default_started_when_frontmatter_value_is_missing_or_invalid(self, tmp_path, frontmatter_lines):
        # Arrange
        path = tmp_path / "ctx.md"
        path.write_text(f"---\n{frontmatter_lines}---\n", encoding="utf-8")

        # Act
        from pipeline_context import PipelineContext
        loaded = PipelineContext.load(path)

        # Assert
        assert abs((loaded.started - datetime.datetime.now()).total_seconds()) < 5


# ---------------------------------------------------------------------------
# Project Configuration section ordering
# ---------------------------------------------------------------------------

class TestPipelineContextProjectConfigurationOrdering:
    def test_save_writes_project_configuration_section_before_workspace_setup_section(self, tmp_path):
        # Arrange
        from pipeline_context import PipelineContext
        ctx = PipelineContext(
            work_item_id="ADR-TEST",
            project_configuration="work_tracking: jira",
            workspace_setup="Cloned repo to /tmp/workspace",
        )
        path = tmp_path / "ctx.md"

        # Act
        ctx.save(path)

        # Assert
        text = path.read_text(encoding="utf-8")
        assert text.index("<!-- section:Project Configuration -->") < text.index("<!-- section:Workspace Setup -->")
