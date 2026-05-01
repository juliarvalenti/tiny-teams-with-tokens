from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    charter: str = ""
    repos: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    confluence_roots: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    webex_channels: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    user_bindings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    ingest_config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    locked: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class Report(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", index=True)
    version: int
    ingested_at: datetime = Field(default_factory=_utcnow)
    summary: str = ""
    is_greenfield: bool = False


class PageRevision(SQLModel, table=True):
    """One row per page mutation. Reading a page = latest row by created_at.
    `report_id` set when the revision was produced by an ingest run; NULL for
    human/chat edits. History viewer queries by (project_id, path)."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", index=True)
    path: str = Field(index=True)
    markdown: str
    author: str = "ttt"
    message: str = ""
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    report_id: UUID | None = Field(default=None, foreign_key="report.id", index=True)


class IngestRun(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", index=True)
    status: str = "pending"  # pending | running | success | failed
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
    error: str | None = None
    log: str = ""


class ChatSession(SQLModel, table=True):
    """One chat thread per project. The Agent SDK persists transcripts to disk
    keyed by `sdk_session_id`; we hold the pointer here so we can resume."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", index=True, unique=True)
    sdk_session_id: str | None = None  # captured from ResultMessage on first turn
    created_at: datetime = Field(default_factory=_utcnow)
    last_used_at: datetime = Field(default_factory=_utcnow)
