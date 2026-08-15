"""PipelineContext dataclass and its save()/load() persistence to/from a
markdown file with YAML-ish frontmatter plus named '<!-- section:Name -->'
body sections.
"""

import datetime
import dataclasses
from dataclasses import dataclass, field

# Fields tagged frontmatter=True below are populated explicitly from YAML
# frontmatter in load(); KNOWN_FRONTMATTER_KEYS (derived at the bottom of this
# module from that tag) is what load() uses to route any other frontmatter key
# into extra_frontmatter instead. Tagging inline keeps the set from drifting
# out of sync as fields are added — there's no separate list to remember to
# update.
FRONTMATTER_FIELD = {"frontmatter": True}


@dataclass
class PipelineContext:
    work_item_id: str = field(metadata=FRONTMATTER_FIELD)
    spec_path: str = field(default="", metadata=FRONTMATTER_FIELD)
    state: str = field(default="init", metadata=FRONTMATTER_FIELD)
    fix_iteration: int = field(default=0, metadata=FRONTMATTER_FIELD)
    review_fix_iteration: int = field(default=0, metadata=FRONTMATTER_FIELD)
    pr_url: str = field(default="", metadata=FRONTMATTER_FIELD)
    build_log: str = field(default="", metadata=FRONTMATTER_FIELD)
    test_log: str = field(default="", metadata=FRONTMATTER_FIELD)
    signoff_cycle_count: int = field(default=0, metadata=FRONTMATTER_FIELD)
    consecutive_failures: int = field(default=0, metadata=FRONTMATTER_FIELD)
    review_cycle_count: int = field(default=0, metadata=FRONTMATTER_FIELD)
    troubleshooter_input: str = field(default="", metadata=FRONTMATTER_FIELD)
    pending_agent: str = field(default="", metadata=FRONTMATTER_FIELD)
    added_to_stack: bool = field(default=False, metadata=FRONTMATTER_FIELD)
    project_configuration: str = ""
    started: datetime.datetime = field(default_factory=datetime.datetime.now, metadata=FRONTMATTER_FIELD)
    last_updated: datetime.datetime = field(default_factory=datetime.datetime.now, metadata=FRONTMATTER_FIELD)
    extra_frontmatter: dict = field(default_factory=dict)
    workspace_setup: str = ""
    debug_report: str = ""
    brief: str = ""
    work_summaries: list = field(default_factory=list)
    review_notes: str = ""
    last_failure: str = ""
    signoff_review: str = ""
    signoff_research: str = ""
    signoff_build_result: str = ""
    validate_result: str = ""
    handoff_result: str = ""

    def save(self, path):
        self.last_updated = datetime.datetime.now()

        lines = [
            "---",
            f"work_item_id: {self.work_item_id}",
            f"spec_path: {self.spec_path}",
            f"state: {self.state}",
            f"fix_iteration: {self.fix_iteration}",
            f"review_fix_iteration: {self.review_fix_iteration}",
            f"pr_url: {self.pr_url}",
            f"build_log: {self.build_log}",
            f"test_log: {self.test_log}",
            f"signoff_cycle_count: {self.signoff_cycle_count}",
            f"consecutive_failures: {self.consecutive_failures}",
            f"review_cycle_count: {self.review_cycle_count}",
            f"troubleshooter_input: {self.troubleshooter_input}",
            f"pending_agent: {self.pending_agent}",
            f"added_to_stack: {self.added_to_stack}",
            f"started: {self.started.isoformat()}",
            f"last_updated: {self.last_updated.isoformat()}",
        ]
        for key, value in self.extra_frontmatter.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"- {item}")
            else:
                lines.append(f"{key}: {value}")
        lines += [
            "---",
            "",
            f"# {self.work_item_id} Dev Team Context",
            "",
        ]

        if self.project_configuration:
            lines += ["<!-- section:Project Configuration -->", "", self.project_configuration.strip(), ""]

        if self.workspace_setup:
            lines += ["<!-- section:Workspace Setup -->", "", self.workspace_setup.strip(), ""]

        if self.debug_report:
            lines += ["<!-- section:Debug Report -->", "", self.debug_report.strip(), ""]

        if self.brief:
            lines += ["<!-- section:Researcher Brief -->", "", self.brief.strip(), ""]

        if self.work_summaries:
            lines += ["<!-- section:Implementation Summary -->", "", self.work_summaries[0].strip(), ""]
            for i, summary in enumerate(self.work_summaries[1:], start=1):
                lines += [f"<!-- section:Fix {i} -->", "", summary.strip(), ""]

        if self.review_notes:
            lines += ["<!-- section:Review Notes -->", "", self.review_notes.strip(), ""]

        if self.last_failure:
            lines += ["<!-- section:Last Failure -->", "", self.last_failure.strip(), ""]

        if self.signoff_review:
            lines += ["<!-- section:Signoff Review -->", "", self.signoff_review.strip(), ""]

        if self.signoff_research:
            lines += ["<!-- section:Signoff Research -->", "", self.signoff_research.strip(), ""]

        if self.signoff_build_result:
            lines += ["<!-- section:Signoff Build Result -->", "", self.signoff_build_result.strip(), ""]

        if self.validate_result:
            lines += ["<!-- section:Validate Result -->", "", self.validate_result.strip(), ""]

        if self.handoff_result:
            lines += ["<!-- section:Handoff Result -->", "", self.handoff_result.strip(), ""]

        log_links = []
        if self.build_log:
            log_links.append(f"- Build: {self.build_log}")
        if self.test_log:
            log_links.append(f"- Tests: {self.test_log}")
        if log_links:
            lines += ["<!-- section:Logs -->", ""] + log_links + [""]

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path):
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        meta = {}
        in_frontmatter = False
        current_list_key = None
        body_start = len(lines)
        for idx, line in enumerate(lines):
            if line == "---":
                if in_frontmatter:
                    body_start = idx + 1
                    break
                in_frontmatter = True
                continue
            if not in_frontmatter:
                continue
            if line.startswith("- ") and current_list_key is not None:
                if not isinstance(meta[current_list_key], list):
                    meta[current_list_key] = []
                meta[current_list_key].append(line[2:])
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if value == "":
                    # May turn out to be a list (if '- ' lines follow) or a
                    # genuinely empty scalar value — resolved lazily above.
                    meta[key] = ""
                    current_list_key = key
                else:
                    meta[key] = value
                    current_list_key = None

        sections = _parse_sections("\n".join(lines[body_start:]))

        ctx = cls(
            work_item_id=meta.get("work_item_id", ""),
            spec_path=meta.get("spec_path", ""),
            state=meta.get("state", "init"),
            fix_iteration=int(meta.get("fix_iteration", 0)),
            review_fix_iteration=int(meta.get("review_fix_iteration", 0)),
            pr_url=meta.get("pr_url", ""),
            build_log=meta.get("build_log", ""),
            test_log=meta.get("test_log", ""),
            signoff_cycle_count=int(meta.get("signoff_cycle_count", 0)),
            consecutive_failures=int(meta.get("consecutive_failures", 0)),
            review_cycle_count=int(meta.get("review_cycle_count", 0)),
            troubleshooter_input=meta.get("troubleshooter_input", ""),
            pending_agent=meta.get("pending_agent", ""),
            added_to_stack=meta.get("added_to_stack", "False").strip().lower() == "true",
        )

        try:
            ctx.started = datetime.datetime.fromisoformat(meta["started"])
            ctx.last_updated = datetime.datetime.fromisoformat(meta["last_updated"])
        except (KeyError, ValueError):
            pass

        ctx.extra_frontmatter = {
            k: v for k, v in meta.items() if k not in KNOWN_FRONTMATTER_KEYS
        }
        ctx.project_configuration = sections.get("Project Configuration", "")
        ctx.workspace_setup = sections.get("Workspace Setup", "")
        ctx.debug_report = sections.get("Debug Report", "")
        ctx.brief = sections.get("Researcher Brief", "")
        ctx.review_notes = sections.get("Review Notes", "")
        ctx.last_failure = sections.get("Last Failure", "")
        ctx.signoff_review = sections.get("Signoff Review", "")
        ctx.signoff_research = sections.get("Signoff Research", "")
        ctx.signoff_build_result = sections.get("Signoff Build Result", "")
        ctx.validate_result = sections.get("Validate Result", "")
        ctx.handoff_result = sections.get("Handoff Result", "")
        if "Implementation Summary" in sections:
            ctx.work_summaries = [sections["Implementation Summary"]]
            i = 1
            while f"Fix {i}" in sections:
                ctx.work_summaries.append(sections[f"Fix {i}"])
                i += 1

        return ctx


# Derived (not hand-maintained) from the fields tagged frontmatter=True above,
# so this can't drift out of sync as fields are added to PipelineContext.
KNOWN_FRONTMATTER_KEYS = {
    f.name for f in dataclasses.fields(PipelineContext)
    if f.metadata.get("frontmatter")
}


def _parse_sections(body: str) -> dict[str, str]:
    """Split a markdown body into {heading: content} by '<!-- section:Name -->' sentinels."""
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in body.split("\n"):
        if line.startswith("<!-- section:") and line.endswith(" -->"):
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = line[len("<!-- section:"):-len(" -->")].strip()
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections
