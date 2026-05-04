import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ttt.db import get_session
from ttt.models import (
    ChatMessage,
    ChatSession,
    ConfluenceSpace,
    IngestRun,
    PageRevision,
    Project,
    Repo,
    Report,
    WebexRoom,
)
from ttt.services.projects import (
    ConfluenceSpaceOut,
    ProjectCreate,
    ProjectSummary,
    ProjectUpdate,
    RepoOut,
    WebexRoomOut,
    add_confluence_space,
    add_repo,
    add_webex_room,
    cancel_project_ingest,
    create_project_with_greenfield,
    list_project_confluence_spaces,
    list_project_repos,
    list_project_summaries,
    list_project_webex_rooms,
    reingest_project,
    summarize,
)

router = APIRouter(tags=["projects"])

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
    latest_run = session.exec(
        select(IngestRun)
        .where(IngestRun.project_id == project_id)
        .order_by(IngestRun.started_at.desc())
    ).first()
    return {
        **summary.model_dump(mode="json"),
        "charter": project.charter,
        "ingest_config": project.ingest_config,
        "repos": [r.model_dump(mode="json") for r in list_project_repos(session, project_id)],
        "webex_rooms": [
            r.model_dump(mode="json") for r in list_project_webex_rooms(session, project_id)
        ],
        "confluence_spaces": [
            r.model_dump(mode="json")
            for r in list_project_confluence_spaces(session, project_id)
        ],
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


# ---------- sources: repos / webex / confluence ----------


class RepoCreate(BaseModel):
    url: str
    slug: str | None = None
    default_branch: str = "main"


@router.get("/projects/{project_id}/repos", response_model=list[RepoOut])
def list_repos(
    project_id: UUID, session: Session = Depends(get_session)
) -> list[RepoOut]:
    return list_project_repos(session, project_id)


@router.post("/projects/{project_id}/repos", response_model=RepoOut)
def create_repo(
    project_id: UUID,
    body: RepoCreate,
    session: Session = Depends(get_session),
) -> RepoOut:
    return add_repo(
        session,
        project_id,
        body.url,
        slug=body.slug,
        default_branch=body.default_branch,
    )


class WebexRoomCreate(BaseModel):
    name: str
    slug: str | None = None
    webex_id: str | None = None


@router.get("/projects/{project_id}/webex", response_model=list[WebexRoomOut])
def list_webex_rooms(
    project_id: UUID, session: Session = Depends(get_session)
) -> list[WebexRoomOut]:
    return list_project_webex_rooms(session, project_id)


@router.post("/projects/{project_id}/webex", response_model=WebexRoomOut)
def create_webex_room(
    project_id: UUID,
    body: WebexRoomCreate,
    session: Session = Depends(get_session),
) -> WebexRoomOut:
    return add_webex_room(
        session, project_id, body.name, slug=body.slug, webex_id=body.webex_id
    )


class ConfluenceSpaceCreate(BaseModel):
    name: str
    space_key: str
    slug: str | None = None
    base_url: str = ""


@router.get("/projects/{project_id}/confluence", response_model=list[ConfluenceSpaceOut])
def list_confluence_spaces(
    project_id: UUID, session: Session = Depends(get_session)
) -> list[ConfluenceSpaceOut]:
    return list_project_confluence_spaces(session, project_id)


@router.post("/projects/{project_id}/confluence", response_model=ConfluenceSpaceOut)
def create_confluence_space(
    project_id: UUID,
    body: ConfluenceSpaceCreate,
    session: Session = Depends(get_session),
) -> ConfluenceSpaceOut:
    return add_confluence_space(
        session,
        project_id,
        body.name,
        body.space_key,
        slug=body.slug,
        base_url=body.base_url,
    )


# ---------- ingest lifecycle ----------


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
    return cancel_project_ingest(session, project_id)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: UUID, session: Session = Depends(get_session)) -> None:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    if project.locked:
        raise HTTPException(409, "project is locked while ingest is running")

    for model in (
        ChatMessage,
        ChatSession,
        PageRevision,
        IngestRun,
        Report,
        Repo,
        WebexRoom,
        ConfluenceSpace,
    ):
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
