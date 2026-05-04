import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ttt.db import get_session
from ttt.models import ChatMessage, ChatSession, IngestRun, PageRevision, Project, Report
from ttt.services.projects import (
    ProjectCreate,
    ProjectSummary,
    ProjectUpdate,
    create_project_with_greenfield,
    list_project_summaries,
    reingest_project,
    summarize,
)

router = APIRouter(tags=["projects"])

# Re-exported for any older import paths.
__all__ = ["router", "ProjectCreate", "ProjectSummary", "ProjectUpdate"]


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(session: Session = Depends(get_session)) -> list[ProjectSummary]:
    return list_project_summaries(session)


@router.post("/projects", response_model=ProjectSummary)
async def create_project(
    body: ProjectCreate, session: Session = Depends(get_session)
) -> ProjectSummary:
    return create_project_with_greenfield(session, body)


@router.get("/projects/{project_id}")
def get_project(project_id: UUID, session: Session = Depends(get_session)) -> dict[str, Any]:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    summary = summarize(session, project)
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
    return summarize(session, project)


class ReingestRequest(BaseModel):
    seed: str | None = None  # optional one-shot instruction for this run


@router.post("/projects/{project_id}/reingest")
async def reingest(
    project_id: UUID,
    body: ReingestRequest | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    seed = body.seed if body else None
    ref = reingest_project(session, project_id, seed=seed)
    return {"run_id": str(ref.run_id), "status": ref.status}


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


@router.post("/projects/{project_id}/ingest/cancel")
def cancel_ingest(
    project_id: UUID, session: Session = Depends(get_session)
) -> dict[str, str]:
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


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: UUID, session: Session = Depends(get_session)) -> None:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    if project.locked:
        raise HTTPException(409, "project is locked while ingest is running")

    for model in (ChatMessage, ChatSession, PageRevision, IngestRun, Report):
        rows = session.exec(select(model).where(model.project_id == project_id)).all()
        for row in rows:
            session.delete(row)

    session.delete(project)
    session.commit()

    wiki_dir = Path("data/wiki") / str(project_id)
    if wiki_dir.exists():
        shutil.rmtree(wiki_dir)


@router.get("/ingest/{run_id}")
def get_ingest(run_id: UUID, session: Session = Depends(get_session)) -> IngestRun:
    run = session.get(IngestRun, run_id)
    if not run:
        raise HTTPException(404, "ingest run not found")
    return run
