"""Workspace-level relationships file.

A single YAML file at `data/relationships.yaml` declares groups (named
buckets of projects, e.g. "Payments Platform") and binary relationships
(e.g. project A `depends_on` project B).

File is the source of truth — agents read/write via MCP tools, UI reads/
writes via the API. No DB tables; just round-trip the file. If the file
is missing, return an empty document.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import yaml

from ttt.config import settings

log = logging.getLogger("ttt.workspace")


RelationshipKind = Literal["depends_on", "blocks", "shares_team", "supersedes"]
ALLOWED_KINDS: frozenset[str] = frozenset(
    ("depends_on", "blocks", "shares_team", "supersedes")
)


@dataclass
class Group:
    id: str
    name: str
    description: str = ""
    projects: list[str] = field(default_factory=list)


@dataclass
class Relationship:
    from_: str
    to: str
    kind: RelationshipKind
    note: str = ""


@dataclass
class WorkspaceDoc:
    groups: list[Group] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "groups": [
                {
                    "id": g.id,
                    "name": g.name,
                    "description": g.description,
                    "projects": list(g.projects),
                }
                for g in self.groups
            ],
            "relationships": [
                {
                    "from": r.from_,
                    "to": r.to,
                    "kind": r.kind,
                    "note": r.note,
                }
                for r in self.relationships
            ],
        }


def _empty() -> WorkspaceDoc:
    return WorkspaceDoc()


def load() -> WorkspaceDoc:
    path = settings.ttt_relationships_path
    if not path.exists():
        return _empty()
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        log.exception("relationships.yaml is malformed; returning empty doc")
        return _empty()
    return _parse(raw)


def save(doc: WorkspaceDoc) -> None:
    path = settings.ttt_relationships_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc.to_dict(), sort_keys=False))


def replace_from_dict(raw: dict) -> WorkspaceDoc:
    """Validate + persist a dict (e.g. from a PUT body or an agent tool call)."""
    doc = _parse(raw)
    save(doc)
    return doc


def _parse(raw: dict) -> WorkspaceDoc:
    """Coerce a raw dict (from YAML or JSON) into a validated WorkspaceDoc.

    Rejects unknown kinds, missing required fields. Extra fields are dropped.
    """
    if not isinstance(raw, dict):
        raise ValueError("relationships document must be a mapping at the top level")

    groups_raw = raw.get("groups") or []
    relationships_raw = raw.get("relationships") or []

    groups: list[Group] = []
    seen_group_ids: set[str] = set()
    for g in groups_raw:
        if not isinstance(g, dict):
            raise ValueError(f"group must be a mapping, got {type(g).__name__}")
        gid = str(g.get("id") or "").strip()
        name = str(g.get("name") or "").strip()
        if not gid:
            raise ValueError("group missing required field: id")
        if not name:
            raise ValueError(f"group {gid!r} missing required field: name")
        if gid in seen_group_ids:
            raise ValueError(f"duplicate group id: {gid!r}")
        seen_group_ids.add(gid)
        groups.append(
            Group(
                id=gid,
                name=name,
                description=str(g.get("description") or ""),
                projects=[str(p) for p in (g.get("projects") or [])],
            )
        )

    relationships: list[Relationship] = []
    for r in relationships_raw:
        if not isinstance(r, dict):
            raise ValueError(f"relationship must be a mapping, got {type(r).__name__}")
        # Accept both "from" (YAML) and "from_" (Python source compat).
        frm = str(r.get("from") or r.get("from_") or "").strip()
        to = str(r.get("to") or "").strip()
        kind = str(r.get("kind") or "").strip()
        if not frm or not to:
            raise ValueError("relationship missing required field: from / to")
        if kind not in ALLOWED_KINDS:
            raise ValueError(
                f"invalid relationship kind: {kind!r}; allowed: {sorted(ALLOWED_KINDS)}"
            )
        relationships.append(
            Relationship(from_=frm, to=to, kind=kind, note=str(r.get("note") or ""))  # type: ignore[arg-type]
        )

    return WorkspaceDoc(groups=groups, relationships=relationships)
