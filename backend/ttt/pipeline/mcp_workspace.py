"""In-process MCP server exposing workspace-level relationships to agents.

Two tools:
- workspace_get_relationships() — read the current YAML doc as JSON
- workspace_update_relationships(doc) — replace it (validated)

Both chat and ingest agents see these. The chat agent uses them for
"what other projects depend on this" questions. The ingest agent may
notice new relationships in deltas (e.g. PR description mentions a sister
repo) and propose updates.
"""

from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from ttt import workspace


def _ok(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}


def _err(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "is_error": True}


def build_workspace_mcp():
    @tool(
        "workspace_get_relationships",
        "Read the workspace relationships doc — groups (named buckets of projects) and binary relationships (depends_on / blocks / shares_team / supersedes) between projects. Returns JSON.",
        {},
    )
    async def get_rel(_args: dict) -> dict[str, Any]:
        return _ok(workspace.load().to_dict())

    @tool(
        "workspace_update_relationships",
        (
            "Replace the workspace relationships doc. Pass the FULL new document — partial updates "
            "are not supported. Schema: {\"groups\": [{id, name, description?, projects:[uuid]}], "
            "\"relationships\": [{from:uuid, to:uuid, kind:depends_on|blocks|shares_team|supersedes, note?}]}. "
            "Pass the document as a JSON string."
        ),
        {"doc_json": str},
    )
    async def update_rel(args: dict) -> dict[str, Any]:
        try:
            raw = json.loads(args["doc_json"])
        except json.JSONDecodeError as e:
            return _err(f"doc_json is not valid JSON: {e}")
        try:
            doc = workspace.replace_from_dict(raw)
        except ValueError as e:
            return _err(f"validation failed: {e}")
        return _ok(doc.to_dict())

    return create_sdk_mcp_server(
        name="workspace",
        version="0.1.0",
        tools=[get_rel, update_rel],
    )
