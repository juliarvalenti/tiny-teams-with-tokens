"""Pipeline orchestrator — wiki shape.

Greenfield ingest:
  - fetch all source data (wide window)
  - extract per-source deltas in parallel
  - founding synthesizer emits all 4 stable pages
  - 3 dynamic-page synthesizers run in parallel, grounded by stable pages
  - all 7 pages committed to git in a single commit

Incremental ingest:
  - fetch source data since last_ingested_at
  - extract per-source deltas in parallel
  - load existing stable pages from prior commit; preserve as-is
  - 3 dynamic-page synthesizers rewrite, grounded by stable pages + prior dynamic page
  - only the 3 dynamic pages re-committed
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session, select

from ttt.config import settings
from ttt.db import engine
from ttt.models import IngestRun, Project, Report
from ttt.pipeline.connectors.base import Connector, FetchResult
from ttt.pipeline.connectors.github import GithubConnector
from ttt.pipeline.connectors.mock import MockConnector
from ttt.pipeline.extractors import extract
from ttt.pipeline.page_synthesizers import (
    write_activity,
    write_conversations,
    write_founding_pages,
    write_status,
)
from ttt.pipeline.page_synthesizers._common import PageInputs
from ttt.reports import repo as report_repo
from ttt.reports import schema as report_schema

log = logging.getLogger("ttt.pipeline")


def default_mock_connectors() -> list[Connector]:
    return [
        MockConnector("github", "github.md"),
        MockConnector("confluence", "confluence.md"),
        MockConnector("webex", "webex.md"),
    ]


def connectors_for(project: Project) -> list[Connector]:
    """Pick a connector per source based on project config + env."""
    chosen: list[Connector] = []
    if project.repos:
        chosen.append(GithubConnector(project.repos, token=settings.github_token))
    else:
        chosen.append(MockConnector("github", "github.md"))
    chosen.append(MockConnector("confluence", "confluence.md"))  # M6
    chosen.append(MockConnector("webex", "webex.md"))  # M7
    return chosen


async def _safe_fetch(conn: Connector, since: datetime | None) -> FetchResult:
    try:
        return await conn.fetch(since=since)
    except Exception as e:
        return FetchResult(
            source=conn.name,
            markdown="",
            skipped=True,
            skip_reason=f"{type(e).__name__}: {e}",
        )


async def run_ingest(
    session: Session,
    project: Project,
    *,
    run: IngestRun,
    connectors: list[Connector] | None = None,
) -> Report:
    connectors = connectors or connectors_for(project)
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

        prior_pages: dict[str, str] = {}
        if prior:
            prior_pages = report_repo.list_pages(project.id)

        # 1. Fetch sources in parallel.
        since = prior.ingested_at if prior else None
        async with asyncio.TaskGroup() as tg:
            fetch_tasks = {c.name: tg.create_task(_safe_fetch(c, since)) for c in connectors}
        results: dict[str, FetchResult] = {n: t.result() for n, t in fetch_tasks.items()}

        # 2. Extract per-source deltas in parallel.
        async def _delta(source: str) -> str:
            r = results.get(source)
            if r is None:
                return f"_{source}: skipped (no connector configured)_"
            return await extract(r)

        async with asyncio.TaskGroup() as tg:
            extract_tasks = {
                source: tg.create_task(_delta(source))
                for source in ("github", "confluence", "webex")
            }
        deltas = {s: t.result() for s, t in extract_tasks.items()}

        # 3. Build stable-page bodies for grounding.
        if is_greenfield:
            stable_inputs = PageInputs(
                project_name=project.name,
                charter=project.charter,
                is_greenfield=True,
                github_delta=deltas["github"],
                confluence_delta=deltas["confluence"],
                webex_delta=deltas["webex"],
                stable_pages={},
            )
            stable_bodies = await write_founding_pages(stable_inputs)
        else:
            # Strip frontmatter from prior stable pages — synthesizers should see only body content.
            stable_bodies = {
                path: report_schema.parse_frontmatter(prior_pages[path])[1].strip()
                for path in report_schema.stable_paths()
                if path in prior_pages
            }
            # If a stable page is missing in the prior version, regenerate the founding pass to fill it.
            if not all(p in stable_bodies for p in report_schema.stable_paths()):
                log.warning("stable pages missing on incremental — re-running founding pass")
                stable_inputs = PageInputs(
                    project_name=project.name,
                    charter=project.charter,
                    is_greenfield=False,
                    github_delta=deltas["github"],
                    confluence_delta=deltas["confluence"],
                    webex_delta=deltas["webex"],
                    stable_pages=stable_bodies,
                )
                stable_bodies.update(await write_founding_pages(stable_inputs))

        # 4. Run dynamic-page synthesizers in parallel.
        def page_inputs(prior_dynamic_path: str) -> PageInputs:
            prior_md = ""
            if prior_dynamic_path in prior_pages:
                prior_md = report_schema.parse_frontmatter(prior_pages[prior_dynamic_path])[1].strip()
            return PageInputs(
                project_name=project.name,
                charter=project.charter,
                is_greenfield=is_greenfield,
                github_delta=deltas["github"],
                confluence_delta=deltas["confluence"],
                webex_delta=deltas["webex"],
                stable_pages=stable_bodies,
                prior_page_md=prior_md,
            )

        async with asyncio.TaskGroup() as tg:
            dynamic_tasks = {
                "status.md": tg.create_task(write_status(page_inputs("status.md"))),
                "activity.md": tg.create_task(write_activity(page_inputs("activity.md"))),
                "conversations.md": tg.create_task(write_conversations(page_inputs("conversations.md"))),
            }
        dynamic_bodies = {p: t.result() for p, t in dynamic_tasks.items()}

        # 5. Compose pages with frontmatter and persist.
        all_pages: dict[str, str] = {}
        if is_greenfield:
            for path in report_schema.stable_paths():
                spec = report_schema.SPEC_BY_PATH[path]
                all_pages[path] = report_schema.page_with_frontmatter(spec, stable_bodies[path])
        else:
            # On incremental, we still re-write stable pages only if we just regenerated some.
            for path in report_schema.stable_paths():
                if path not in prior_pages:
                    spec = report_schema.SPEC_BY_PATH[path]
                    all_pages[path] = report_schema.page_with_frontmatter(spec, stable_bodies[path])

        for path, body in dynamic_bodies.items():
            spec = report_schema.SPEC_BY_PATH[path]
            all_pages[path] = report_schema.page_with_frontmatter(spec, body)

        next_version = (prior.version + 1) if prior else 1
        report = Report(
            project_id=project.id,
            version=next_version,
            summary="",
            is_greenfield=is_greenfield,
        )
        session.add(report)
        session.commit()
        session.refresh(report)

        report_repo.write_pages(
            project.id,
            all_pages,
            message=f"ingest v{next_version} ({'greenfield' if is_greenfield else 'incremental'})",
            author="ttt-pipeline",
            report_id=report.id,
        )

        committed_pages = report_repo.list_pages(project.id)
        missing = report_schema.validate_pages(committed_pages)
        if missing:
            log.warning("v%d missing required pages after write: %s", next_version, missing)
        report.summary = _summary_from_overview(committed_pages)
        session.add(report)
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        session.add(run)
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
    """Pull the first non-heading paragraph from overview.md as the project tile summary."""
    md = pages.get("overview.md", "")
    if not md:
        return ""
    _, body = report_schema.parse_frontmatter(md)
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("_("):
            continue
        return line[:200]
    return ""


async def dispatch_ingest(project_id: UUID, run_id: UUID) -> None:
    """Background-task entrypoint."""
    try:
        with Session(engine) as session:
            project = session.get(Project, project_id)
            run = session.get(IngestRun, run_id)
            if not project or not run:
                log.error("dispatch_ingest: missing project or run (%s, %s)", project_id, run_id)
                return
            await run_ingest(session, project, run=run)
    except Exception:
        log.exception("ingest pipeline failed for project=%s run=%s", project_id, run_id)
