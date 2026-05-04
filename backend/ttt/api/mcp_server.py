"""MCP server mounted on the FastAPI app.

Exposes two tools to MCP clients (e.g. Claude Code):
  ttt_list_projects  — list all projects with name + id
  ttt_ask            — send a message to a project's chat agent; returns the response

Mount point: GET/POST /mcp  (SSE transport, auto-negotiated by FastMCP)
Register in Claude Code settings:
  {
    "mcpServers": {
      "ttt": { "type": "sse", "url": "http://localhost:8765/mcp/sse" }
    }
  }
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from sqlmodel import Session, select

from ttt.chat.agent import stream_chat
from ttt.db import engine
from ttt.models import ChatSession, Project, Report

log = logging.getLogger("ttt.mcp")

mcp = FastMCP("ttt", instructions="Tools for querying Tiny Teams with Tokens project wikis.")


@mcp.tool()
def ttt_list_projects() -> list[dict]:
    """List all TTT projects with their id, name, and latest report version."""
    with Session(engine) as session:
        projects = session.exec(select(Project)).all()
        out = []
        for p in projects:
            latest = session.exec(
                select(Report)
                .where(Report.project_id == p.id)
                .order_by(Report.version.desc())
            ).first()
            out.append({
                "id": str(p.id),
                "name": p.name,
                "latest_version": latest.version if latest else None,
                "locked": p.locked,
            })
        return out


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
        # Grab existing sdk_session_id so we can resume the conversation thread.
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

    # Collect the full streamed response.
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
