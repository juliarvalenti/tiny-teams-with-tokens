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
    IngestRunRef,
    ProjectCreate,
    ProjectSummary,
    cancel_project_ingest,
    create_project_with_greenfield,
    list_project_summaries,
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
    confluence_roots: list[str] | None = None,
    webex_channels: list[str] | None = None,
    user_bindings: dict[str, Any] | None = None,
    ingest_config: dict[str, Any] | None = None,
) -> ProjectSummary:
    """Create a new TTT project and kick off a greenfield ingest.

    Args mirror `ProjectCreate`. The greenfield ingest runs in the background
    against the configured repos; poll `ttt_list_projects` to watch the
    `latest_version` field appear once the first ingest completes.
    """
    body = ProjectCreate(
        name=name,
        charter=charter,
        repos=repos or [],
        confluence_roots=confluence_roots or [],
        webex_channels=webex_channels or [],
        user_bindings=user_bindings or {},
        ingest_config=ingest_config or {},
    )
    with Session(engine) as session:
        return create_project_with_greenfield(session, body)


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
