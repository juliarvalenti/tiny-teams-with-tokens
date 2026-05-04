"""Ingest dispatch — the only entrypoint the API/services layer calls.

Always routes to the Claude Agent SDK loop in `agent_ingestor.py`. The old
fan-out static path (extractors + synthesizers + per-source connectors) is
gone; if you want to add a new source, build it as an in-process MCP server
the agent can call (see `mcp_github.py` for the pattern).
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session

from ttt.db import engine
from ttt.models import IngestRun, Project

log = logging.getLogger("ttt.pipeline.runner")


async def dispatch_ingest(
    project_id: UUID, run_id: UUID, *, seed: str | None = None
) -> None:
    """Background-task entrypoint. Loads the Project + IngestRun, then runs
    the agent loop. Exceptions are caught and logged so a background-task
    failure doesn't crash the event loop."""
    try:
        with Session(engine) as session:
            project = session.get(Project, project_id)
            run = session.get(IngestRun, run_id)
            if not project or not run:
                log.error(
                    "dispatch_ingest: missing project or run (%s, %s)", project_id, run_id
                )
                return
            from ttt.pipeline.agent_ingestor import run_agent_ingest

            await run_agent_ingest(session, project, run=run, seed=seed)
    except Exception:
        log.exception("ingest pipeline failed for project=%s run=%s", project_id, run_id)
