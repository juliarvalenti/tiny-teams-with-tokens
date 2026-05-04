"""Agent-based ingest — replaces the static fan-out pipeline with a Claude
Agent SDK loop. The agent has the wiki on disk (Read/Edit/Write/Glob/Grep)
plus an in-process GitHub MCP server. It walks the page schema, decides
what to fetch, and writes pages directly.

Feature-flagged via `settings.ingest_mode = "agent"`. The static path in
`runner.py` stays as the default until this is trusted.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import json

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from sqlmodel import Session, select

from ttt.db import engine
from ttt.models import IngestRun, Project, Report
from ttt.config import settings
from ttt.pipeline.agent_core import build_agent_options, build_citation_guidance
from ttt.reports import repo as report_repo
from ttt.reports import schema as report_schema

log = logging.getLogger("ttt.pipeline.agent")

INGEST_MODEL = settings.ingest_model
MAX_TURNS = 60


def _build_system_prompt(
    project: Project,
    is_greenfield: bool,
    repos: list[str],
) -> str:
    page_lines: list[str] = []
    for spec in report_schema.DEFAULT_PAGES:
        grounded = (
            f" — grounded by: {', '.join(spec.grounded_by)}"
            if spec.grounded_by
            else ""
        )
        page_lines.append(
            f"  - `{spec.path}` ({spec.kind}) — {spec.title}{grounded}"
        )

    mode_block = (
        "MODE: GREENFIELD.\n\n"
        "The wiki is empty. Write all the seed pages listed below. Default kind for each is shown — write that into the YAML frontmatter."
        if is_greenfield
        else (
            "MODE: INCREMENTAL.\n\n"
            "The page kind is declared in each page's YAML frontmatter (`kind: stable|dynamic|hidden|report`). "
            "**The frontmatter is authoritative — trust it, not the page path.** Users may have pinned pages as stable "
            "or flipped the kind on existing ones.\n\n"
            "- READ every existing page first.\n"
            "- DO NOT rewrite pages with `kind: stable` — they're pinned by the user.\n"
            "- DO NOT rewrite pages with `kind: hidden` unless the user explicitly asks. You MAY append short dated notes to `memory.md` if there's something worth remembering across ingests.\n"
            "- Rewrite pages with `kind: dynamic` and `kind: report`. Preserve their frontmatter; only the body should change.\n"
            "- If a custom page exists with a kind you don't recognize, leave it alone.\n"
        )
    )

    repos_block = (
        f"GITHUB REPOS: {', '.join(repos)}" if repos else "GITHUB REPOS: (none configured)"
    )

    return f"""You are running the status-report ingest for project "{project.name}".

Your job is to produce a status wiki — a tree of markdown pages — that captures what the project is and what's currently happening with it. The wiki is in your current working directory; you'll read existing pages, fetch source data via the github tools, and write or update pages.

PROJECT CHARTER (seed context, may be empty):
{project.charter or "(empty)"}

{repos_block}

PAGE STRUCTURE — these pages exist or should be created:

{chr(10).join(page_lines)}

The `memory.md` (kind: hidden) page is YOUR working memory. It's not surfaced to users by default. Read it on every ingest. You may append short notes to it that you want to remember across ingests — context that didn't fit anywhere else, recurring patterns, things you noticed about how this team works. Keep entries dated and tight.

Each page has YAML frontmatter you MUST preserve / write:

```
---
title: <Title>
kind: <stable|dynamic|report>
order: <integer>
[grounded_by: [comma, separated, list]]
---
```

Stable pages are human-curated identity (purpose, team, glossary, architecture). Dynamic pages are agent-rewritten snapshots filtered against the stable anchor. The standup is a tight TL;DR card with fixed sections.

{mode_block}

PROCESS:
1. Read existing pages with Read/Glob to understand current state.
2. Use the github tools (mcp__github__*) to fetch recent commits, issues, PRs, releases, CODEOWNERS as needed.
3. Write each page with Write. Keep frontmatter intact.
4. Be tight and grounded. No vibes. If activity didn't move a goal, say so explicitly — silence is information.

{build_citation_guidance(project.repos)}

STANDUP STRUCTURE (`standup.md`) — exact 4 H2 sections, in this order:
- `## What is this` (one or two sentences)
- `## Headline` (one or two sentences — the single most important thing this period)
- `## Asks / Blockers` (bullets — anything blocked or needing help; cite items)
- `## Up next` (bullets — upcoming milestones / deadlines)

Total under ~200 words for the standup.

STATUS STRUCTURE (`status.md`) — H2 sections: `## Goal progress`, `## Headline this period`, `## Decisions made`, `## Things that surprised us`. Cite every claim.

ACTIVITY STRUCTURE (`activity.md`) — Filtered list of activity, organized by goal from overview.md.

CONVERSATIONS STRUCTURE (`conversations.md`) — Decisions made, open questions, escalations from chat (we don't have Webex yet, so this section will be sparse — that's fine).

When all pages are written, reply with a one-line summary of what you produced. Do NOT include the page bodies in your reply."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _append_log(run_id: UUID, line: str) -> None:
    """Append a line to IngestRun.log so the frontend can poll and render
    a Docker-style stream while the agent runs."""
    try:
        with Session(engine) as ses:
            run = ses.get(IngestRun, run_id)
            if not run:
                return
            run.log = (run.log or "") + line + "\n"
            ses.add(run)
            ses.commit()
    except Exception:
        log.exception("failed to append ingest log")


def _stringify_tool_input(value: object) -> str:
    try:
        return json.dumps(value, separators=(", ", "="))[:300]
    except Exception:
        return str(value)[:300]


def _make_log_on_write(run_id: UUID):
    """Closure for the shared persist hook's `on_write` callback — emits the
    Docker-log line so the IngestRun.log stream shows file writes."""

    def _log(page_path: str, byte_count: int) -> None:
        _append_log(run_id, f"[{_now_iso()}] ✎ wrote {page_path} ({byte_count} bytes)")

    return _log


async def run_agent_ingest(
    session: Session,
    project: Project,
    *,
    run: IngestRun,
    seed: str | None = None,
) -> Report:
    """Run an ingest as a Claude Agent SDK loop. Returns the new Report row.
    `seed` is an optional one-shot user instruction passed alongside the
    standard greenfield/incremental directive."""
    project.locked = True
    run.status = "running"
    session.add_all([project, run])
    session.commit()

    try:
        prior = session.exec(
            select(Report)
            .where(Report.project_id == project.id)
            .order_by(Report.version.desc())
        ).first()
        is_greenfield = prior is None
        next_version = (prior.version + 1) if prior else 1

        # Pre-create the Report so the persist hook can tag revisions with it.
        report = Report(
            project_id=project.id,
            version=next_version,
            summary="",
            is_greenfield=is_greenfield,
        )
        session.add(report)
        session.commit()
        session.refresh(report)

        options = build_agent_options(
            project_id=project.id,
            project_repos=project.repos,
            system_prompt=_build_system_prompt(project, is_greenfield, project.repos),
            model=INGEST_MODEL,
            max_turns=MAX_TURNS,
            persist_author="ttt-pipeline",
            report_id=report.id,
            on_write=_make_log_on_write(run.id),
        )

        prompt_parts = [
            f"Run a {'GREENFIELD' if is_greenfield else 'INCREMENTAL'} ingest for "
            f"\"{project.name}\". Begin by reading the existing wiki pages, then fetch "
            f"recent activity and update pages per the system prompt."
        ]
        if seed and seed.strip():
            prompt_parts.append(
                "\n\nUSER SEED INSTRUCTION (one-shot focus for this run — interpret "
                "alongside the standard process; do not let it override page-kind "
                "preservation rules):\n"
                f"{seed.strip()}"
            )
        prompt = "".join(prompt_parts)

        _append_log(
            run.id,
            f"[{_now_iso()}] ▶ agent ingest started "
            f"(mode={'greenfield' if is_greenfield else 'incremental'}, model={INGEST_MODEL})",
        )
        _append_log(run.id, f"[{_now_iso()}] · repos: {', '.join(project.repos) or '(none)'}")
        if seed and seed.strip():
            _append_log(run.id, f"[{_now_iso()}] · seed: {seed.strip()[:200]}")

        tool_call_count = 0
        tool_call_names: dict[str, str] = {}  # id -> short tool label
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        tool_call_count += 1
                        short = block.name.replace("mcp__github__", "gh.")
                        tool_call_names[block.id] = short
                        args_str = _stringify_tool_input(block.input)
                        _append_log(
                            run.id,
                            f"[{_now_iso()}] → {short} {args_str}",
                        )
                    elif isinstance(block, TextBlock):
                        text = (block.text or "").strip()
                        if text:
                            for line in text.splitlines():
                                if line.strip():
                                    _append_log(run.id, f"[{_now_iso()}] ~ {line}")
            elif isinstance(message, UserMessage):
                # Tool results — note the tool returned, no need to dump bodies.
                for block in getattr(message, "content", []) or []:
                    kind = getattr(block, "type", None) or (
                        block.get("type") if isinstance(block, dict) else None
                    )
                    if kind == "tool_result":
                        tool_id = getattr(block, "tool_use_id", None) or (
                            block.get("tool_use_id") if isinstance(block, dict) else None
                        )
                        is_error = getattr(block, "is_error", False) or (
                            block.get("is_error", False) if isinstance(block, dict) else False
                        )
                        label = tool_call_names.get(tool_id or "", "?")
                        marker = "✗" if is_error else "←"
                        _append_log(run.id, f"[{_now_iso()}] {marker} {label} returned")
            elif isinstance(message, SystemMessage):
                if message.subtype == "init":
                    _append_log(run.id, f"[{_now_iso()}] · agent session opened")
            elif isinstance(message, ResultMessage):
                cost = getattr(message, "total_cost_usd", None)
                turns = getattr(message, "num_turns", None)
                cost_str = f"${cost:.4f}" if isinstance(cost, (int, float)) else "?"
                _append_log(
                    run.id,
                    f"[{_now_iso()}] ✓ agent finished "
                    f"(subtype={message.subtype}, turns={turns}, tool_calls={tool_call_count}, cost={cost_str})",
                )

        # Validation: confirm all required pages exist after the agent finished.
        committed = report_repo.list_pages(project.id)
        missing = report_schema.validate_pages(committed)
        if missing:
            log.warning(
                "v%d missing required pages after agent run: %s", next_version, missing
            )

        # No need to re-attach revisions — the persist hook tagged them with
        # report.id at write time.
        report.summary = _summary_from_overview(committed)
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        session.add_all([report, run])
        session.commit()
        session.refresh(report)
        return report

    except Exception as e:
        run.status = "failed"
        run.error = f"{type(e).__name__}: {e}"
        run.finished_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()
        raise
    finally:
        project.locked = False
        session.add(project)
        session.commit()


def _summary_from_overview(pages: dict[str, str]) -> str:
    md = pages.get("overview.md", "")
    if not md:
        return ""
    _, body = report_schema.parse_frontmatter(md)
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("_("):
            continue
        return line[:200]
    return ""
