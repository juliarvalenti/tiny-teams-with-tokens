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
from pathlib import Path
from uuid import UUID

import json

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from sqlmodel import Session, select

from ttt.config import settings
from ttt.db import engine
from ttt.models import IngestRun, PageRevision, Project, Report
from ttt.pipeline.mcp_github import build_github_mcp
from ttt.reports import repo as report_repo
from ttt.reports import schema as report_schema

log = logging.getLogger("ttt.pipeline.agent")

INGEST_MODEL = "claude-haiku-4-5"
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
        "MODE: GREENFIELD. The wiki is empty. Write ALL 8 pages."
        if is_greenfield
        else (
            "MODE: INCREMENTAL. The 4 stable pages already exist; READ them first to "
            "understand the project, but DO NOT rewrite them. Rewrite only the dynamic "
            "and report pages: `status.md`, `activity.md`, `conversations.md`, `standup.md`."
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

PAGE STRUCTURE — there are 8 pages:

{chr(10).join(page_lines)}

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
2. Use the github tools (mcp__github__*) to fetch recent commits, issues, PRs, releases, CODEOWNERS as needed. Cite specific items in pages: `[commit a1b2c3d]`, `[issue #142]`, `[PR #99]`.
3. Write each page with Write. Keep frontmatter intact.
4. Be tight and grounded. No vibes. If activity didn't move a goal, say so explicitly — silence is information.

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


def _make_record_hook(project_id: UUID, run_id: UUID):
    """PostToolUse hook: every Edit/Write of a wiki file → PageRevision row.
    Also appends a "wrote <path>" line to the ingest log."""

    project_dir = (settings.ttt_wiki_dir / str(project_id)).resolve()

    async def record(input_data, _tool_use_id, _context):
        tool_name = input_data.get("tool_name", "")
        if tool_name not in {"Edit", "Write"}:
            return {}
        tool_input = input_data.get("tool_input") or {}
        file_path = tool_input.get("file_path") or tool_input.get("path")
        if not file_path:
            return {}
        try:
            abs_path = Path(file_path).resolve()
            rel = abs_path.relative_to(project_dir)
        except (ValueError, OSError):
            return {}
        if not abs_path.exists():
            return {}
        try:
            content = abs_path.read_text()
            page_path = str(rel).replace("\\", "/")
            report_repo.write_page(
                project_id,
                page_path,
                content,
                message=f"agent ingest: {page_path}",
                author="ttt-pipeline",
            )
            _append_log(run_id, f"[{_now_iso()}] ✎ wrote {page_path} ({len(content)} bytes)")
        except Exception:
            log.exception("agent persist failed for %s", file_path)
        return {}

    return record


async def run_agent_ingest(
    session: Session,
    project: Project,
    *,
    run: IngestRun,
) -> Report:
    """Run an ingest as a Claude Agent SDK loop. Returns the new Report row."""
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

        # Sync filesystem cache to disk so the agent's Read tool sees current state.
        report_repo.sync_to_disk(project.id)
        project_dir = (settings.ttt_wiki_dir / str(project.id))
        project_dir.mkdir(parents=True, exist_ok=True)

        # Pre-create the Report so PostToolUse hook can attach revisions to it.
        report = Report(
            project_id=project.id,
            version=next_version,
            summary="",
            is_greenfield=is_greenfield,
        )
        session.add(report)
        session.commit()
        session.refresh(report)

        gh_server = build_github_mcp(project.repos, token=settings.github_token)

        options = ClaudeAgentOptions(
            cwd=str(project_dir),
            allowed_tools=[
                "Read",
                "Edit",
                "Write",
                "Glob",
                "Grep",
                "mcp__github__github_list_commits",
                "mcp__github__github_list_releases",
                "mcp__github__github_list_issues",
                "mcp__github__github_get_issue",
                "mcp__github__github_list_pulls",
                "mcp__github__github_get_pr",
                "mcp__github__github_search_issues",
                "mcp__github__github_get_codeowners",
            ],
            permission_mode="acceptEdits",
            system_prompt=_build_system_prompt(project, is_greenfield, project.repos),
            model=INGEST_MODEL,
            setting_sources=[],
            mcp_servers={"github": gh_server},
            env={
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                "ANTHROPIC_API_KEY": settings.anthropic_api_key,
            },
            max_turns=MAX_TURNS,
            hooks={
                "PostToolUse": [
                    HookMatcher(matcher="Edit|Write", hooks=[_make_record_hook(project.id, run.id)])
                ],
            },
        )

        prompt = (
            f"Run a {'GREENFIELD' if is_greenfield else 'INCREMENTAL'} ingest for "
            f"\"{project.name}\". Begin by reading the existing wiki pages, then fetch "
            f"recent activity and update pages per the system prompt."
        )

        _append_log(
            run.id,
            f"[{_now_iso()}] ▶ agent ingest started "
            f"(mode={'greenfield' if is_greenfield else 'incremental'}, model={INGEST_MODEL})",
        )
        _append_log(run.id, f"[{_now_iso()}] · repos: {', '.join(project.repos) or '(none)'}")

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
                                    _append_log(run.id, f"[{_now_iso()}] ▒ {line}")
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

        # Re-attach the agent's revisions to this report row so history is queryable.
        with Session(engine) as ses:
            ses.exec(
                select(PageRevision)
                .where(
                    PageRevision.project_id == project.id,
                    PageRevision.report_id.is_(None),
                    PageRevision.author == "ttt-pipeline",
                    PageRevision.created_at >= report.ingested_at,
                )
            )
            revs = ses.exec(
                select(PageRevision)
                .where(
                    PageRevision.project_id == project.id,
                    PageRevision.report_id.is_(None),
                    PageRevision.author == "ttt-pipeline",
                    PageRevision.created_at >= report.ingested_at,
                )
            ).all()
            for r in revs:
                r.report_id = report.id
                ses.add(r)
            ses.commit()

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
