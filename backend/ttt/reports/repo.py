"""Sqlite-backed page store.

Wiki pages live in the `pagerevision` table. Each save inserts a new row;
reading a page is `latest row by created_at` for `(project_id, path)`. A
filesystem cache at `data/wiki/<project_id>/<path>` mirrors the current
state so the chat agent's Read/Edit/Write/Glob tools can operate on real
files. Sqlite is the source of truth; the filesystem is regenerable.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, select

from ttt.config import settings
from ttt.db import engine
from ttt.models import PageRevision


def _wiki_root() -> Path:
    return settings.ttt_wiki_dir


def init_store() -> None:
    """Idempotent: ensure the wiki cache directory exists."""
    _wiki_root().mkdir(parents=True, exist_ok=True)


def _project_dir(project_id: UUID) -> Path:
    d = _wiki_root() / str(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_page_path(page_path: str) -> str:
    """Reject path traversal; require a `.md` suffix; normalize separators."""
    if not page_path or page_path.startswith("/") or page_path.endswith("/"):
        raise ValueError(f"invalid page path: {page_path!r}")
    parts = page_path.split("/")
    if any(p in {"", ".", ".."} for p in parts):
        raise ValueError(f"invalid page path component: {page_path!r}")
    if not page_path.endswith(".md"):
        raise ValueError(f"page path must end with .md: {page_path!r}")
    return page_path


def _mirror_to_disk(project_id: UUID, page_path: str, markdown: str) -> None:
    target = _project_dir(project_id) / page_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def write_pages(
    project_id: UUID,
    pages: dict[str, str],
    *,
    message: str,
    author: str = "ttt",
    report_id: UUID | None = None,
) -> None:
    """Write multiple pages: one PageRevision row per page, all with the same
    timestamp + message. Mirrors to disk so the chat agent can Read them."""
    now = _utcnow()
    with Session(engine) as session:
        for page_path, md in pages.items():
            safe = _safe_page_path(page_path)
            session.add(
                PageRevision(
                    project_id=project_id,
                    path=safe,
                    markdown=md,
                    author=author,
                    message=message,
                    created_at=now,
                    report_id=report_id,
                )
            )
            _mirror_to_disk(project_id, safe, md)
        session.commit()


def write_page(
    project_id: UUID,
    page_path: str,
    markdown: str,
    *,
    message: str,
    author: str = "ttt",
    report_id: UUID | None = None,
) -> None:
    """Single-page write."""
    write_pages(
        project_id,
        {page_path: markdown},
        message=message,
        author=author,
        report_id=report_id,
    )


def read_page(project_id: UUID, page_path: str) -> str:
    """Latest revision of a single page. Raises LookupError if missing or
    if the latest revision is a tombstone (deleted)."""
    safe = _safe_page_path(page_path)
    with Session(engine) as session:
        rev = session.exec(
            select(PageRevision)
            .where(PageRevision.project_id == project_id, PageRevision.path == safe)
            .order_by(PageRevision.created_at.desc(), PageRevision.id.desc())
        ).first()
    if not rev or rev.deleted:
        raise LookupError(f"page not found: {page_path}")
    return rev.markdown


def list_pages(project_id: UUID) -> dict[str, str]:
    """Return the current state: for each path, the latest revision. Paths
    whose latest revision is a tombstone are skipped."""
    with Session(engine) as session:
        rows = session.exec(
            select(PageRevision)
            .where(PageRevision.project_id == project_id)
            .order_by(PageRevision.path, PageRevision.created_at.desc(), PageRevision.id.desc())
        ).all()
    out: dict[str, str] = {}
    for r in rows:
        if r.path in out:
            continue
        if r.deleted:
            # Tombstone wins; remember so a later revision (older row) doesn't resurrect.
            out[r.path] = ""
        else:
            out[r.path] = r.markdown
    return {p: md for p, md in out.items() if md != ""}


def delete_page(
    project_id: UUID,
    page_path: str,
    *,
    author: str = "ttt",
    message: str = "",
) -> None:
    """Tombstone the page — insert a deleted=True PageRevision so reads skip
    it. History rows remain. Idempotent: deleting an already-deleted page is a
    no-op-equivalent (just adds another tombstone row)."""
    safe = _safe_page_path(page_path)
    now = _utcnow()
    with Session(engine) as session:
        session.add(
            PageRevision(
                project_id=project_id,
                path=safe,
                markdown="",
                author=author,
                message=message or f"deleted {safe}",
                created_at=now,
                deleted=True,
            )
        )
        session.commit()
    # Remove the FS mirror so the chat agent's Glob/Read doesn't see a stale file.
    target = _project_dir(project_id) / safe
    if target.exists():
        target.unlink()


def page_history(project_id: UUID, page_path: str) -> list[PageRevision]:
    """All revisions of a single page, newest first. For #1 history viewer."""
    safe = _safe_page_path(page_path)
    with Session(engine) as session:
        return list(
            session.exec(
                select(PageRevision)
                .where(PageRevision.project_id == project_id, PageRevision.path == safe)
                .order_by(PageRevision.created_at.desc(), PageRevision.id.desc())
            ).all()
        )


def sync_to_disk(project_id: UUID) -> None:
    """Rebuild the filesystem cache from sqlite. Useful if the cache is wiped
    or if a new chat session needs to be sure the FS is current."""
    pages = list_pages(project_id)
    pdir = _project_dir(project_id)
    if pdir.exists():
        shutil.rmtree(pdir)
    pdir.mkdir(parents=True, exist_ok=True)
    for path, md in pages.items():
        _mirror_to_disk(project_id, path, md)
