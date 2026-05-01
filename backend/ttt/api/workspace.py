"""Workspace-level API — relationships file (groups, dependencies)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ttt import workspace

router = APIRouter(tags=["workspace"])


@router.get("/workspace/relationships")
def get_relationships() -> dict[str, Any]:
    return workspace.load().to_dict()


@router.put("/workspace/relationships")
def put_relationships(body: dict[str, Any]) -> dict[str, Any]:
    try:
        doc = workspace.replace_from_dict(body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return doc.to_dict()
