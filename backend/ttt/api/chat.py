"""Chat endpoint — Server-Sent Events streaming the Claude Agent SDK loop."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from ttt.chat.agent import stream_chat
from ttt.db import engine, get_session
from ttt.models import ChatMessage, ChatSession, Project, Report
from ttt.reports import repo as report_repo

log = logging.getLogger("ttt.api.chat")

router = APIRouter(tags=["chat"])


class ChatTurnRequest(BaseModel):
    message: str


def _get_or_create_session(session: Session, project_id: UUID) -> ChatSession:
    chat = session.exec(
        select(ChatSession).where(ChatSession.project_id == project_id)
    ).first()
    if chat:
        return chat
    chat = ChatSession(project_id=project_id)
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return chat


def _latest_stable_pages(project_id: UUID) -> dict[str, str]:
    """Return the current stable pages for the project (path → markdown).
    Empty dict if no report exists yet."""
    with Session(engine) as ses:
        report = ses.exec(
            select(Report)
            .where(Report.project_id == project_id)
            .order_by(Report.version.desc())
        ).first()
        if not report:
            return {}
    pages = report_repo.list_pages(project_id)
    return {p: pages[p] for p in pages if p in {"overview.md", "team.md", "glossary.md", "architecture.md"}}


@router.get("/projects/{project_id}/chat")
def get_chat_state(
    project_id: UUID, session: Session = Depends(get_session)
) -> dict:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    chat = _get_or_create_session(session, project_id)
    return {
        "project_id": str(project_id),
        "session_id": str(chat.id),
        "sdk_session_id": chat.sdk_session_id,
        "created_at": chat.created_at.isoformat(),
        "last_used_at": chat.last_used_at.isoformat(),
    }


@router.post("/projects/{project_id}/chat/reset")
def reset_chat(
    project_id: UUID, session: Session = Depends(get_session)
) -> dict:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    chat = _get_or_create_session(session, project_id)
    chat.sdk_session_id = None
    chat.last_used_at = datetime.now(timezone.utc)
    session.add(chat)

    # Wipe the user-facing transcript too. The Agent SDK's own transcript on
    # disk is keyed off the (now-cleared) sdk_session_id, so it's effectively
    # orphaned — fine for a PoC.
    msgs = session.exec(
        select(ChatMessage).where(ChatMessage.project_id == project_id)
    ).all()
    for m in msgs:
        session.delete(m)
    session.commit()
    return {"ok": True}


@router.get("/projects/{project_id}/chat/messages")
def list_messages(
    project_id: UUID, session: Session = Depends(get_session)
) -> list[dict]:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    rows = session.exec(
        select(ChatMessage)
        .where(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at)
    ).all()
    return [
        {
            "id": str(r.id),
            "role": r.role,
            "text": r.text,
            "error": r.error,
            "tool_calls": r.tool_calls or [],
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/projects/{project_id}/chat")
async def post_chat_turn(
    project_id: UUID,
    body: ChatTurnRequest,
    session: Session = Depends(get_session),
) -> EventSourceResponse:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    chat = _get_or_create_session(session, project_id)
    sdk_session_id = chat.sdk_session_id

    # Snapshot stable pages NOW so the system prompt is consistent for this turn.
    stable_pages = _latest_stable_pages(project_id)

    chat_id = chat.id  # capture for the generator (session is request-scoped)
    pid = project_id

    async def event_generator() -> AsyncIterator[dict]:
        captured_session_id: str | None = None
        # Roll up the assistant's final state from the stream so we can persist
        # one ChatMessage row at end-of-turn.
        assistant_text = ""
        assistant_error: str | None = None
        tool_calls: dict[str, dict] = {}
        try:
            async for event in stream_chat(
                project=project,
                user_message=body.message,
                sdk_session_id=sdk_session_id,
                stable_pages=stable_pages,
            ):
                if event.type == "session":
                    captured_session_id = event.data.get("session_id") or captured_session_id
                elif event.type == "token":
                    assistant_text += event.data.get("text", "")
                elif event.type == "tool_call":
                    tc_id = event.data.get("id") or ""
                    tool_calls[tc_id] = {
                        "id": tc_id,
                        "tool": event.data.get("tool"),
                        "input": event.data.get("input"),
                        "status": "running",
                    }
                elif event.type == "tool_result":
                    tc_id = event.data.get("id") or ""
                    if tc_id in tool_calls:
                        tool_calls[tc_id]["preview"] = event.data.get("preview")
                        tool_calls[tc_id]["truncated"] = event.data.get("truncated")
                        tool_calls[tc_id]["status"] = "done"
                elif event.type == "done":
                    captured_session_id = event.data.get("session_id") or captured_session_id
                    if not assistant_text.strip() and event.data.get("result"):
                        assistant_text = event.data["result"]
                elif event.type == "error":
                    assistant_error = event.data.get("message")
                yield {"event": event.type, "data": json.dumps(event.data)}
        finally:
            with Session(engine) as ses:
                # Persist the SDK session id so the next turn can resume.
                if captured_session_id:
                    fresh = ses.get(ChatSession, chat_id)
                    if fresh:
                        fresh.sdk_session_id = captured_session_id
                        fresh.last_used_at = datetime.now(timezone.utc)
                        ses.add(fresh)
                # Persist the user + assistant turn for replay on next page load.
                ses.add(ChatMessage(project_id=pid, role="user", text=body.message))
                ses.add(
                    ChatMessage(
                        project_id=pid,
                        role="assistant",
                        text=assistant_text,
                        error=assistant_error,
                        tool_calls=list(tool_calls.values()),
                    )
                )
                ses.commit()

    return EventSourceResponse(event_generator())
