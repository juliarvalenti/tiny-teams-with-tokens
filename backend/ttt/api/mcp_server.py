"""MCP server mounted on the FastAPI app.

Exposes tools to MCP clients (e.g. Claude Code):
  ttt_list_projects   — list all projects (typed: ProjectSummary)
  ttt_create_project  — create a new project + kick off greenfield ingest
  ttt_ask             — send a message to a project's chat agent

Mount point: GET/POST /mcp  (Streamable HTTP transport).

All schemas are imported from `ttt.services.projects` so the MCP boundary
binds to the same Pydantic models as the HTTP API.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from sqlmodel import Session, select

from ttt.chat.agent import stream_chat
from ttt.db import engine
from ttt.models import ChatSession, Project, Report
from ttt.services.projects import (
    ConfluenceSpaceOut,
    IngestRunDetail,
    IngestRunRef,
    ProjectCreate,
    ProjectSummary,
    RepoOut,
    WebexRoomOut,
    add_confluence_space,
    add_repo,
    add_webex_room,
    cancel_project_ingest,
    create_project_with_greenfield,
    get_ingest_run_detail,
    latest_ingest_run_for_project,
    list_project_confluence_spaces,
    list_project_repos,
    list_project_summaries,
    list_project_webex_rooms,
    reingest_project,
)

log = logging.getLogger("ttt.mcp")

mcp = FastMCP(
    "ttt",
    instructions="Tools for querying Tiny Teams with Tokens project wikis.",
)


@mcp.tool()
def ttt_list_projects() -> list[ProjectSummary]:
    """List all TTT projects with id, name, locked state, and latest report version."""
    with Session(engine) as session:
        return list_project_summaries(session)


@mcp.tool()
def ttt_create_project(
    name: str,
    charter: str = "",
    repos: list[str] | None = None,
    phase: str | None = None,
    cadence: str | None = None,
    user_bindings: dict[str, Any] | None = None,
    ingest_config: dict[str, Any] | None = None,
) -> ProjectSummary:
    """Create a new TTT project and kick off a greenfield ingest.

    Args:
        name: Display name (e.g. "Internet of Cognition").
        charter: Free-form one-paragraph "what is this and why".
        repos: GitHub repo URLs / `owner/name` strings to seed as Repos.
        phase: Lifecycle phase (prototype | venture | active | sunset).
        cadence: Expected change cadence (weekly | monthly | quiet).
        user_bindings: Free-form metadata.
        ingest_config: Free-form ingest knobs.

    Webex rooms and Confluence spaces are added separately via
    `ttt_add_webex_room` / `ttt_add_confluence_space` after creation.
    """
    body = ProjectCreate(
        name=name,
        charter=charter,
        phase=phase,
        cadence=cadence,
        repos=repos or [],
        user_bindings=user_bindings or {},
        ingest_config=ingest_config or {},
    )
    with Session(engine) as session:
        return create_project_with_greenfield(session, body)


# ---------- source attachment ----------


@mcp.tool()
def ttt_list_repos(project_id: str) -> list[RepoOut]:
    """List GitHub repos attached to a project."""
    pid = _parse_uuid(project_id, "project_id")
    with Session(engine) as session:
        return list_project_repos(session, pid)


@mcp.tool()
def ttt_add_repo(
    project_id: str,
    url: str,
    slug: str | None = None,
    default_branch: str = "main",
) -> RepoOut:
    """Attach a GitHub repo to a project. The repo's content lands in the
    wiki under `repos/<slug>/...` after the next ingest. `slug` defaults to
    the repo's last path segment (e.g. `mycelium-io/mycelium` → `mycelium`)."""
    pid = _parse_uuid(project_id, "project_id")
    with Session(engine) as session:
        return add_repo(session, pid, url, slug=slug, default_branch=default_branch)


@mcp.tool()
def ttt_list_webex_rooms(project_id: str) -> list[WebexRoomOut]:
    """List Webex rooms attached to a project."""
    pid = _parse_uuid(project_id, "project_id")
    with Session(engine) as session:
        return list_project_webex_rooms(session, pid)


@mcp.tool()
def ttt_add_webex_room(
    project_id: str,
    name: str,
    slug: str | None = None,
    webex_id: str | None = None,
) -> WebexRoomOut:
    """Attach a Webex room to a project. Synthesized into `webex/<slug>/...`
    once the Webex connector is wired. `name` is the human display name
    (e.g. `"IoC::Mycelium::SRE"`); `slug` defaults to a slugified version."""
    pid = _parse_uuid(project_id, "project_id")
    with Session(engine) as session:
        return add_webex_room(session, pid, name, slug=slug, webex_id=webex_id)


@mcp.tool()
def ttt_list_confluence_spaces(project_id: str) -> list[ConfluenceSpaceOut]:
    """List Confluence spaces attached to a project."""
    pid = _parse_uuid(project_id, "project_id")
    with Session(engine) as session:
        return list_project_confluence_spaces(session, pid)


@mcp.tool()
def ttt_add_confluence_space(
    project_id: str,
    name: str,
    space_key: str,
    slug: str | None = None,
    base_url: str = "",
) -> ConfluenceSpaceOut:
    """Attach a Confluence space to a project. Synthesized into
    `confluence/<slug>/...` once the Confluence connector is wired."""
    pid = _parse_uuid(project_id, "project_id")
    with Session(engine) as session:
        return add_confluence_space(
            session, pid, name, space_key, slug=slug, base_url=base_url
        )


def _parse_uuid(raw: str, field: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError as e:
        raise ValueError(f"invalid {field}: {raw!r}") from e


@mcp.tool()
def ttt_reingest(project_id: str, seed: str | None = None) -> IngestRunRef:
    """Kick off an incremental ingest for a project.

    The ingest runs in the background; the returned `run_id` can be polled
    via the HTTP API (`GET /api/ingest/{run_id}`). `seed` is an optional
    one-shot instruction that biases this single run (e.g. "focus on the
    auth refactor").

    Args:
        project_id: The UUID of the project (from ttt_list_projects).
        seed: Optional one-shot focus instruction for this run.
    """
    try:
        pid = UUID(project_id)
    except ValueError as e:
        raise ValueError(f"invalid project_id {project_id!r}") from e
    with Session(engine) as session:
        return reingest_project(session, pid, seed=seed)


@mcp.tool()
def ttt_cancel_ingest(project_id: str) -> dict[str, str]:
    """Cancel a project's in-flight ingest and unlock the project.

    Use this to recover when an ingest process died (e.g. backend restart)
    and left `locked: true`. Marks the latest pending/running IngestRun as
    failed with `cancelled by user`.

    Args:
        project_id: The UUID of the project (from ttt_list_projects).
    """
    try:
        pid = UUID(project_id)
    except ValueError as e:
        raise ValueError(f"invalid project_id {project_id!r}") from e
    with Session(engine) as session:
        return cancel_project_ingest(session, pid)


@mcp.tool()
def ttt_get_ingest_log(
    run_id: str | None = None, project_id: str | None = None, tail: int = 0
) -> IngestRunDetail:
    """Fetch the log + status of an ingest run.

    Pass exactly one of `run_id` (a specific run) or `project_id` (the latest
    run for that project). `tail` (lines) trims the log to the last N lines —
    use 0 for the full buffer.

    Args:
        run_id: UUID of a specific IngestRun (from ttt_reingest).
        project_id: UUID of a project — fetches its most recent run.
        tail: If > 0, return only the last N log lines.
    """
    if bool(run_id) == bool(project_id):
        raise ValueError("pass exactly one of run_id or project_id")
    with Session(engine) as session:
        try:
            target = UUID(run_id or project_id)  # type: ignore[arg-type]
        except ValueError as e:
            raise ValueError("invalid uuid") from e
        detail = (
            get_ingest_run_detail(session, target)
            if run_id
            else latest_ingest_run_for_project(session, target)
        )
    if tail > 0 and detail.log:
        lines = detail.log.splitlines()
        detail = detail.model_copy(update={"log": "\n".join(lines[-tail:])})
    return detail


@mcp.tool()
async def ttt_ask(project_id: str, question: str) -> str:
    """Ask the chat agent a question about a specific project wiki.

    The agent has full access to the project's wiki pages and GitHub data.
    Returns the agent's complete response as a string.

    Args:
        project_id: The UUID of the project (from ttt_list_projects).
        question: The question or instruction to send to the agent.
    """
    try:
        pid = UUID(project_id)
    except ValueError:
        return f"Error: invalid project_id {project_id!r}"

    with Session(engine) as session:
        project = session.get(Project, pid)
        if not project:
            return f"Error: project {project_id} not found"
        chat = session.exec(
            select(ChatSession).where(ChatSession.project_id == pid)
        ).first()
        sdk_session_id = chat.sdk_session_id if chat else None

        latest = session.exec(
            select(Report)
            .where(Report.project_id == pid)
            .order_by(Report.version.desc())
        ).first()

    if not latest:
        return "Error: no report exists for this project yet — run an ingest first."

    text_parts: list[str] = []
    error_msg: str | None = None

    try:
        async for event in stream_chat(
            project=project,
            user_message=question,
            sdk_session_id=sdk_session_id,
            stable_pages={},
        ):
            if event.type == "token":
                text_parts.append(event.data.get("text", ""))
            elif event.type == "done":
                if not text_parts and event.data.get("result"):
                    text_parts.append(event.data["result"])
            elif event.type == "error":
                error_msg = event.data.get("message")
    except Exception as e:
        log.exception("ttt_ask failed for project %s", project_id)
        return f"Error: {type(e).__name__}: {e}"

    if error_msg:
        return f"Error from agent: {error_msg}"
    return "".join(text_parts).strip() or "(agent returned no text)"
