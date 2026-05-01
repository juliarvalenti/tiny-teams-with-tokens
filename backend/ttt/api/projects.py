import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ttt.db import get_session
from ttt.models import IngestRun, Project, Report
from ttt.pipeline.runner import dispatch_ingest

router = APIRouter(tags=["projects"])


def _start_ingest(session: Session, project: Project) -> IngestRun:
    """Create an IngestRun row and schedule the pipeline as a background task."""
    if project.locked:
        raise HTTPException(409, "ingest already in progress")
    run = IngestRun(project_id=project.id, status="pending")
    project.locked = True
    session.add_all([run, project])
    session.commit()
    session.refresh(run)
    asyncio.create_task(dispatch_ingest(project.id, run.id))
    return run


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


def _summarize(session: Session, project: Project) -> ProjectSummary:
    latest = session.exec(
        select(Report).where(Report.project_id == project.id).order_by(Report.version.desc())
    ).first()
    return ProjectSummary(
        id=project.id,
        name=project.name,
        locked=project.locked,
        created_at=project.created_at,
        latest_version=latest.version if latest else None,
        latest_ingested_at=latest.ingested_at if latest else None,
    )


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(session: Session = Depends(get_session)) -> list[ProjectSummary]:
    projects = session.exec(select(Project)).all()
    return [_summarize(session, p) for p in projects]


@router.post("/projects", response_model=ProjectSummary)
async def create_project(
    body: ProjectCreate, session: Session = Depends(get_session)
) -> ProjectSummary:
    project = Project(**body.model_dump())
    session.add(project)
    session.commit()
    session.refresh(project)
    _start_ingest(session, project)  # greenfield
    return _summarize(session, project)


@router.get("/projects/{project_id}")
def get_project(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, Any]:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    summary = _summarize(session, project)
    # Newest IngestRun for this project — UI uses this to stream the running
    # agent's log into the "ingest in progress" surface.
    latest_run = session.exec(
        select(IngestRun)
        .where(IngestRun.project_id == project_id)
        .order_by(IngestRun.started_at.desc())
    ).first()
    return {
        **summary.model_dump(),
        "charter": project.charter,
        "repos": project.repos,
        "confluence_roots": project.confluence_roots,
        "webex_channels": project.webex_channels,
        "ingest_config": project.ingest_config,
        "latest_run_id": str(latest_run.id) if latest_run else None,
    }


@router.patch("/projects/{project_id}", response_model=ProjectSummary)
def update_project(
    project_id: UUID, body: ProjectUpdate, session: Session = Depends(get_session)
) -> ProjectSummary:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    if project.locked:
        raise HTTPException(409, "project is locked while ingest is running")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(project, k, v)
    session.add(project)
    session.commit()
    session.refresh(project)
    return _summarize(session, project)


@router.post("/projects/{project_id}/reingest")
async def reingest(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, Any]:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    run = _start_ingest(session, project)
    return {"run_id": str(run.id), "status": run.status}


@router.get("/projects/{project_id}/ingests")
def list_ingests(
    project_id: UUID, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    runs = session.exec(
        select(IngestRun)
        .where(IngestRun.project_id == project_id)
        .order_by(IngestRun.started_at.desc())
    ).all()
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "started_at": r.started_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "error": r.error,
            "log_lines": (r.log or "").count("\n"),
        }
        for r in runs
    ]


@router.get("/ingest/{run_id}")
def get_ingest(run_id: UUID, session: Session = Depends(get_session)) -> IngestRun:
    run = session.get(IngestRun, run_id)
    if not run:
        raise HTTPException(404, "ingest run not found")
    return run
