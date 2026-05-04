"""Project service — schemas + business logic shared between the HTTP API
and the MCP server. Keep the route handlers and tool wrappers thin; put
the actual work here so both surfaces bind to the same types and behavior.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
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
