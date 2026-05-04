"""Project service — schemas + business logic shared between the HTTP API
and the MCP server. Keep the route handlers and tool wrappers thin; put
the actual work here so both surfaces bind to the same types and behavior.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ttt.models import IngestRun, Project, Report
from ttt.pipeline.runner import dispatch_ingest


# ---------- shared schemas ----------


class ProjectCreate(BaseModel):
    name: str
    charter: str = ""
    repos: list[str] = []
    confluence_roots: list[str] = []
    webex_channels: list[str] = []
    user_bindings: dict[str, Any] = {}
    ingest_config: dict[str, Any] = {}


class ProjectUpdate(BaseModel):
    charter: str | None = None
    repos: list[str] | None = None
    confluence_roots: list[str] | None = None
    webex_channels: list[str] | None = None
    user_bindings: dict[str, Any] | None = None
    ingest_config: dict[str, Any] | None = None


class ProjectSummary(BaseModel):
    id: UUID
    name: str
    locked: bool
    created_at: datetime
    latest_version: int | None
    latest_ingested_at: datetime | None


class IngestRunRef(BaseModel):
    run_id: UUID
    project_id: UUID
    status: str


class IngestRunDetail(BaseModel):
    run_id: UUID
    project_id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    log: str


# ---------- helpers ----------


def summarize(session: Session, project: Project) -> ProjectSummary:
    latest = session.exec(
        select(Report)
        .where(Report.project_id == project.id)
        .order_by(Report.version.desc())
    ).first()
    return ProjectSummary(
        id=project.id,
        name=project.name,
        locked=project.locked,
        created_at=project.created_at,
        latest_version=latest.version if latest else None,
        latest_ingested_at=latest.ingested_at if latest else None,
    )


def list_project_summaries(session: Session) -> list[ProjectSummary]:
    projects = session.exec(select(Project)).all()
    return [summarize(session, p) for p in projects]


def start_ingest(
    session: Session, project: Project, *, seed: str | None = None
) -> IngestRun:
    """Create an IngestRun row and schedule the pipeline as a background task.
    Raises HTTPException(409) if the project is already locked."""
    if project.locked:
        raise HTTPException(409, "ingest already in progress")
    run = IngestRun(
        project_id=project.id,
        status="pending",
        log=f"[seed] {seed}\n" if seed and seed.strip() else "",
    )
    project.locked = True
    session.add_all([run, project])
    session.commit()
    session.refresh(run)
    asyncio.create_task(dispatch_ingest(project.id, run.id, seed=seed or None))
    return run


def create_project_with_greenfield(
    session: Session, body: ProjectCreate
) -> ProjectSummary:
    """Create the Project row and kick off a greenfield ingest."""
    project = Project(**body.model_dump())
    session.add(project)
    session.commit()
    session.refresh(project)
    start_ingest(session, project)
    return summarize(session, project)


def reingest_project(
    session: Session, project_id: UUID, *, seed: str | None = None
) -> IngestRunRef:
    """Look up a project by id and kick off an incremental ingest.
    Raises HTTPException(404) if missing, (409) if already locked."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    run = start_ingest(session, project, seed=seed)
    return IngestRunRef(run_id=run.id, project_id=project.id, status=run.status)


def get_ingest_run_detail(session: Session, run_id: UUID) -> IngestRunDetail:
    """Fetch a single IngestRun by id with its full log buffer."""
    run = session.get(IngestRun, run_id)
    if not run:
        raise HTTPException(404, "ingest run not found")
    return IngestRunDetail(
        run_id=run.id,
        project_id=run.project_id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        log=run.log or "",
    )


def latest_ingest_run_for_project(
    session: Session, project_id: UUID
) -> IngestRunDetail:
    """Fetch the most recent IngestRun for a project."""
    if not session.get(Project, project_id):
        raise HTTPException(404, "project not found")
    run = session.exec(
        select(IngestRun)
        .where(IngestRun.project_id == project_id)
        .order_by(IngestRun.started_at.desc())
    ).first()
    if not run:
        raise HTTPException(404, "no ingest runs for this project")
    return get_ingest_run_detail(session, run.id)


def cancel_project_ingest(session: Session, project_id: UUID) -> dict[str, str]:
    """Mark the latest pending/running IngestRun as failed and unlock the
    project. Use this to recover a project whose ingest process died (e.g.
    backend restart) and left the lock set."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    if not project.locked:
        raise HTTPException(409, "no ingest in progress")
    run = session.exec(
        select(IngestRun)
        .where(IngestRun.project_id == project_id)
        .order_by(IngestRun.started_at.desc())
    ).first()
    if run and run.status in ("pending", "running"):
        run.status = "failed"
        run.error = "cancelled by user"
        run.finished_at = datetime.now(timezone.utc)
        session.add(run)
    project.locked = False
    session.add(project)
    session.commit()
    return {"status": "cancelled"}
