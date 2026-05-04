from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    """A strategic effort that owns a wiki and a set of sources (Repos,
    WebexRooms, ConfluenceSpaces). The wiki has cross-cutting top-level pages
    (overview, product, architecture, marketing, conversations, standup) plus
    per-source subtrees (`repos/<slug>/...`, `webex/<slug>/...`,
    `confluence/<slug>/...`)."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    charter: str = ""
    phase: str | None = None  # prototype | venture | active | sunset
    cadence: str | None = None  # weekly | monthly | quiet
    user_bindings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    ingest_config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    locked: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class Repo(SQLModel, table=True):
    """A GitHub repo attached to a Project. Slug is the short name used in
    page paths (`repos/<slug>/...`) — defaults to the repo's last path
    segment, user can override on collision."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", index=True)
    slug: str = Field(index=True)
    url: str  # canonical "owner/name" or full https URL
    default_branch: str = "main"
    created_at: datetime = Field(default_factory=_utcnow)


class WebexRoom(SQLModel, table=True):
    """A Webex room attached to a Project. Synthesized into
    `webex/<slug>/...` pages."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", index=True)
    slug: str = Field(index=True)
    name: str  # display name, e.g. "IoC::Mycelium::SRE"
    webex_id: str | None = None  # populated when we wire the connector
    created_at: datetime = Field(default_factory=_utcnow)


class ConfluenceSpace(SQLModel, table=True):
    """A Confluence space attached to a Project. Synthesized into
    `confluence/<slug>/...` pages."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", index=True)
    slug: str = Field(index=True)
    name: str
    space_key: str  # e.g. "IOC"
    base_url: str = ""  # e.g. "https://example.atlassian.net/wiki"
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
    human/chat edits. History viewer queries by (project_id, path).

    `deleted` is a tombstone flag — a revision with deleted=True hides the
    page from list_pages() / read_page(). The history rows remain so audits
    can see what was there. A subsequent non-deleted revision un-tombstones."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", index=True)
    path: str = Field(index=True)
    markdown: str
    author: str = "ttt"
    message: str = ""
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    report_id: UUID | None = Field(default=None, foreign_key="report.id", index=True)
    deleted: bool = False


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


class ChatMessage(SQLModel, table=True):
    """User-facing transcript: one row per completed turn (user message or
    assistant response). Distinct from the Agent SDK's own transcript, which
    is keyed by `sdk_session_id` and contains tool_use blocks etc.

    On chat reset, rows for the project are deleted along with the SDK
    session id. Hydrating the UI on mount = SELECT WHERE project_id ORDER BY
    created_at."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id", index=True)
    role: str  # "user" | "assistant"
    text: str = ""
    error: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, index=True)
