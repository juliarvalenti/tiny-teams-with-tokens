"""Project service — schemas + business logic shared between the HTTP API
and the MCP server. Keep the route handlers and tool wrappers thin; put
the actual work here so both surfaces bind to the same types and behavior.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ttt.models import (
    ConfluenceSpace,
    IngestRun,
    Project,
    Repo,
    Report,
    WebexRoom,
)
from ttt.pipeline.runner import dispatch_ingest


# ---------- shared schemas ----------


class ProjectCreate(BaseModel):
    name: str
    charter: str = ""
    phase: str | None = None
    cadence: str | None = None
    repos: list[str] = []  # github URLs / "owner/name" strings; seeded as Repos
    user_bindings: dict[str, Any] = {}
    ingest_config: dict[str, Any] = {}


class ProjectUpdate(BaseModel):
    charter: str | None = None
    phase: str | None = None
    cadence: str | None = None
    user_bindings: dict[str, Any] | None = None
    ingest_config: dict[str, Any] | None = None


class ProjectSummary(BaseModel):
    id: UUID
    name: str
    locked: bool
    created_at: datetime
    phase: str | None
    cadence: str | None
    repo_count: int
    webex_room_count: int
    confluence_space_count: int
    latest_version: int | None
    latest_ingested_at: datetime | None


class RepoOut(BaseModel):
    id: UUID
    project_id: UUID
    slug: str
    url: str
    default_branch: str


class WebexRoomOut(BaseModel):
    id: UUID
    project_id: UUID
    slug: str
    name: str
    webex_id: str | None


class ConfluenceSpaceOut(BaseModel):
    id: UUID
    project_id: UUID
    slug: str
    name: str
    space_key: str
    base_url: str


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


# ---------- slug helpers ----------


_SLUG_SAFE = re.compile(r"[^a-z0-9-]+")


def _slugify(raw: str) -> str:
    s = raw.strip().lower().replace("::", "-").replace("/", "-").replace("_", "-")
    s = re.sub(r"\s+", "-", s)
    s = _SLUG_SAFE.sub("", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unnamed"


def _normalize_repo_url(raw: str) -> str:
    """`https://github.com/foo/bar.git` → `foo/bar`. Returns the canonical
    `owner/name` form. Leaves anything we can't parse alone."""
    s = raw.strip().rstrip("/")
    for prefix in ("https://github.com/", "github.com/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    if s.endswith(".git"):
        s = s[: -len(".git")]
    parts = s.split("/")
    if len(parts) >= 2 and parts[0] and parts[1]:
        return f"{parts[0]}/{parts[1]}"
    return s


def _repo_slug_from_url(url: str, taken: set[str]) -> str:
    canonical = _normalize_repo_url(url)
    parts = canonical.split("/")
    candidate = _slugify(parts[-1] if parts else canonical)
    if candidate not in taken:
        return candidate
    # Collision — fall back to owner-name
    if len(parts) >= 2:
        candidate = _slugify(f"{parts[0]}-{parts[1]}")
        if candidate not in taken:
            return candidate
    # Last resort: numeric suffix
    i = 2
    while f"{candidate}-{i}" in taken:
        i += 1
    return f"{candidate}-{i}"


# ---------- helpers ----------


def _count(session: Session, model, project_id: UUID) -> int:
    return len(session.exec(select(model).where(model.project_id == project_id)).all())


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
        phase=project.phase,
        cadence=project.cadence,
        repo_count=_count(session, Repo, project.id),
        webex_room_count=_count(session, WebexRoom, project.id),
        confluence_space_count=_count(session, ConfluenceSpace, project.id),
        latest_version=latest.version if latest else None,
        latest_ingested_at=latest.ingested_at if latest else None,
    )


def list_project_summaries(session: Session) -> list[ProjectSummary]:
    projects = session.exec(select(Project)).all()
    return [summarize(session, p) for p in projects]


def list_project_repos(session: Session, project_id: UUID) -> list[RepoOut]:
    rows = session.exec(select(Repo).where(Repo.project_id == project_id)).all()
    return [
        RepoOut(
            id=r.id,
            project_id=r.project_id,
            slug=r.slug,
            url=r.url,
            default_branch=r.default_branch,
        )
        for r in rows
    ]


def list_project_webex_rooms(session: Session, project_id: UUID) -> list[WebexRoomOut]:
    rows = session.exec(
        select(WebexRoom).where(WebexRoom.project_id == project_id)
    ).all()
    return [
        WebexRoomOut(
            id=r.id, project_id=r.project_id, slug=r.slug, name=r.name, webex_id=r.webex_id
        )
        for r in rows
    ]


def list_project_confluence_spaces(
    session: Session, project_id: UUID
) -> list[ConfluenceSpaceOut]:
    rows = session.exec(
        select(ConfluenceSpace).where(ConfluenceSpace.project_id == project_id)
    ).all()
    return [
        ConfluenceSpaceOut(
            id=r.id,
            project_id=r.project_id,
            slug=r.slug,
            name=r.name,
            space_key=r.space_key,
            base_url=r.base_url,
        )
        for r in rows
    ]


def add_repo(
    session: Session,
    project_id: UUID,
    url: str,
    *,
    slug: str | None = None,
    default_branch: str = "main",
) -> RepoOut:
    if not session.get(Project, project_id):
        raise HTTPException(404, "project not found")
    canonical = _normalize_repo_url(url)
    existing = session.exec(
        select(Repo).where(Repo.project_id == project_id)
    ).all()
    taken = {r.slug for r in existing}
    chosen_slug = _slugify(slug) if slug else _repo_slug_from_url(canonical, taken)
    if chosen_slug in taken:
        raise HTTPException(409, f"repo slug {chosen_slug!r} already exists in this project")
    repo = Repo(
        project_id=project_id,
        slug=chosen_slug,
        url=canonical,
        default_branch=default_branch,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return RepoOut(
        id=repo.id,
        project_id=repo.project_id,
        slug=repo.slug,
        url=repo.url,
        default_branch=repo.default_branch,
    )


def add_webex_room(
    session: Session,
    project_id: UUID,
    name: str,
    *,
    slug: str | None = None,
    webex_id: str | None = None,
) -> WebexRoomOut:
    if not session.get(Project, project_id):
        raise HTTPException(404, "project not found")
    chosen_slug = _slugify(slug or name)
    existing = session.exec(
        select(WebexRoom).where(WebexRoom.project_id == project_id)
    ).all()
    if chosen_slug in {r.slug for r in existing}:
        raise HTTPException(409, f"webex room slug {chosen_slug!r} already exists")
    room = WebexRoom(
        project_id=project_id, slug=chosen_slug, name=name, webex_id=webex_id
    )
    session.add(room)
    session.commit()
    session.refresh(room)
    return WebexRoomOut(
        id=room.id,
        project_id=room.project_id,
        slug=room.slug,
        name=room.name,
        webex_id=room.webex_id,
    )


def add_confluence_space(
    session: Session,
    project_id: UUID,
    name: str,
    space_key: str,
    *,
    slug: str | None = None,
    base_url: str = "",
) -> ConfluenceSpaceOut:
    if not session.get(Project, project_id):
        raise HTTPException(404, "project not found")
    chosen_slug = _slugify(slug or space_key or name)
    existing = session.exec(
        select(ConfluenceSpace).where(ConfluenceSpace.project_id == project_id)
    ).all()
    if chosen_slug in {r.slug for r in existing}:
        raise HTTPException(409, f"confluence space slug {chosen_slug!r} already exists")
    space = ConfluenceSpace(
        project_id=project_id,
        slug=chosen_slug,
        name=name,
        space_key=space_key,
        base_url=base_url,
    )
    session.add(space)
    session.commit()
    session.refresh(space)
    return ConfluenceSpaceOut(
        id=space.id,
        project_id=space.project_id,
        slug=space.slug,
        name=space.name,
        space_key=space.space_key,
        base_url=space.base_url,
    )


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
    """Create the Project row, seed Repos from the body, and kick off a
    greenfield ingest. Sources for Webex / Confluence are added separately
    via `add_webex_room` / `add_confluence_space` since neither connector is
    wired yet."""
    project = Project(
        name=body.name,
        charter=body.charter,
        phase=body.phase,
        cadence=body.cadence,
        user_bindings=body.user_bindings,
        ingest_config=body.ingest_config,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    for url in body.repos:
        add_repo(session, project.id, url)
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
