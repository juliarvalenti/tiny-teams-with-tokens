"""Chat agent — wraps the Claude Agent SDK with project-scoped config.

The wiki's working clone is the agent's `cwd`, so the SDK's built-in Read /
Edit / Write / Glob / Grep operate on the wiki natively. After every Edit
or Write, a PostToolUse hook commits the file to the report git repo with
author `ttt-chat` so chat edits show up in `git log` like any other change.

No Bash tool — that's the biggest blast-radius reducer. GitHub deep-dives
go through WebFetch on api.github.com instead of shelling out to `gh`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from claude_agent_sdk.types import StreamEvent

from ttt.models import Project
from ttt.pipeline.agent_core import build_agent_options
from ttt.reports import schema as report_schema

log = logging.getLogger("ttt.chat")

CHAT_MODEL = "claude-sonnet-4-6"
MAX_TURNS = 20


# ---------- SSE event shape ----------

@dataclass
class ChatEvent:
    """A single event the API streams back to the browser as SSE."""

    type: str  # "token" | "tool_call" | "tool_result" | "session" | "done" | "error"
    data: dict[str, Any]


# ---------- system prompt ----------

def build_system_prompt(project: Project, stable_pages: dict[str, str]) -> str:
    """Inject project anchor (overview/team/glossary) into the system prompt
    so Claude has identity + goals before any tool call."""

    def _strip(path: str) -> str:
        md = stable_pages.get(path, "")
        if not md:
            return "_(empty)_"
        _, body = report_schema.parse_frontmatter(md)
        return body.strip() or "_(empty)_"

    return f"""You are an assistant for the project "{project.name}". You help engineering leadership and PMs understand and update the project's status wiki.

The wiki is a tree of markdown files in your current working directory. There are two kinds of pages:
- **stable** (overview, team, glossary, architecture): human-curated. Reingest preserves these. Edit only when explicitly asked.
- **dynamic** (status, activity, conversations): the ingest pipeline rewrites these on each run. You may edit them, but a future ingest will overwrite your edits.

Pages declare their kind in YAML frontmatter (`kind: stable` | `kind: dynamic`). Preserve frontmatter when editing.

You can:
- Read any page in the working directory (Read, Glob, Grep).
- Edit existing pages or create new ones (Edit, Write). Your edits are committed to git automatically; you don't need to run any git commands.
- Pull live context from the web (WebFetch on https://api.github.com/* for issues/PRs/commits, WebSearch for general questions).

You CANNOT run shell commands; there is no Bash tool. If you find yourself wanting to run `gh` or `git`, use WebFetch against api.github.com instead.

Project anchor (read these before answering substantive questions about identity / goals / jargon):

# Overview

{_strip("overview.md")}

# Team

{_strip("team.md")}

# Glossary

{_strip("glossary.md")}

When you reference wiki content, cite it like `(see overview.md)`. When you fetch external information, cite the URL. When you edit a page, briefly summarize what you changed in your reply. Be concise; the reader is scanning."""


# ---------- streaming entrypoint ----------

async def stream_chat(
    *,
    project: Project,
    user_message: str,
    sdk_session_id: str | None,
    stable_pages: dict[str, str],
) -> AsyncIterator[ChatEvent]:
    """Run one chat turn against the Agent SDK and yield ChatEvents the API
    layer can fan out to SSE."""

    options = build_agent_options(
        project_id=project.id,
        project_repos=project.repos,
        system_prompt=build_system_prompt(project, stable_pages),
        model=CHAT_MODEL,
        max_turns=MAX_TURNS,
        persist_author="ttt-chat",
        report_id=None,  # chat edits aren't tied to a Report row
        resume=sdk_session_id,
        include_partial_messages=True,
    )

    try:
        async for message in query(prompt=user_message, options=options):
            async for event in _translate(message):
                yield event
    except Exception as e:
        log.exception("chat stream failed")
        yield ChatEvent(type="error", data={"message": f"{type(e).__name__}: {e}"})


async def _translate(message: Any) -> AsyncIterator[ChatEvent]:
    """Convert SDK messages into ChatEvents."""
    if isinstance(message, StreamEvent):
        ev = message.event or {}
        ev_type = ev.get("type")
        if ev_type == "content_block_delta":
            delta = ev.get("delta") or {}
            if delta.get("type") == "text_delta":
                yield ChatEvent(type="token", data={"text": delta.get("text", "")})
        return

    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                yield ChatEvent(
                    type="tool_call",
                    data={
                        "tool": block.name,
                        "input": _safe_input(block.input),
                        "id": block.id,
                    },
                )
        return

    if isinstance(message, UserMessage):
        for block in getattr(message, "content", []) or []:
            kind = getattr(block, "type", None) or (
                block.get("type") if isinstance(block, dict) else None
            )
            if kind == "tool_result":
                content = (
                    getattr(block, "content", None)
                    or (block.get("content") if isinstance(block, dict) else None)
                    or ""
                )
                preview = _stringify_preview(content)
                yield ChatEvent(
                    type="tool_result",
                    data={
                        "id": getattr(block, "tool_use_id", None)
                        or (block.get("tool_use_id") if isinstance(block, dict) else None),
                        "preview": preview[:600],
                        "truncated": len(preview) > 600,
                    },
                )
        return

    if isinstance(message, SystemMessage):
        if message.subtype == "init":
            sid = (message.data or {}).get("session_id")
            if sid:
                yield ChatEvent(type="session", data={"session_id": sid})
        return

    if isinstance(message, ResultMessage):
        text = ""
        if message.subtype == "success" and message.result:
            text = message.result
        yield ChatEvent(
            type="done",
            data={
                "session_id": message.session_id,
                "subtype": message.subtype,
                "result": text,
                "cost_usd": getattr(message, "total_cost_usd", None),
                "num_turns": getattr(message, "num_turns", None),
            },
        )
        return


def _safe_input(value: Any) -> Any:
    """Make tool input JSON-serializable + trim long string fields for SSE."""
    try:
        json.dumps(value)
    except TypeError:
        value = {"_repr": str(value)[:400]}
    if isinstance(value, dict):
        return {k: (v[:400] + "…" if isinstance(v, str) and len(v) > 400 else v) for k, v in value.items()}
    return value


def _stringify_preview(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(json.dumps(item)[:200])
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


_ = TextBlock  # keep import alive for type-checkers
