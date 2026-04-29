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
    git_commit: str
    ingested_at: datetime = Field(default_factory=_utcnow)
    summary: str = ""
    is_greenfield: bool = False


class IngestRun(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", index=True)
    status: str = "pending"  # pending | running | success | failed
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
    error: str | None = None
    log: str = ""
