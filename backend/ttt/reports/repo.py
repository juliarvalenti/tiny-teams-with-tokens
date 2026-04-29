"""Git operations for the report repo.

Each project's reports live as a tree of markdown pages under
`<project_id>/<page-path>` in a single bare repo at TTT_REPORT_REPO. We
shell out to `git` via subprocess to avoid pulling in a heavy Python git
library.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import UUID

from ttt.config import settings


def _run(args: list[str], cwd: Path) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.rstrip("\n")


def _bare() -> Path:
    return settings.ttt_report_repo


def _wc() -> Path:
    return settings.ttt_report_worktree


def init_report_repo() -> None:
    """Idempotent: ensure bare repo + working clone exist."""
    bare = _bare()
    wc = _wc()
    bare.parent.mkdir(parents=True, exist_ok=True)

    if not (bare / "HEAD").exists():
        bare.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(bare)],
            check=True,
            capture_output=True,
        )

    if not (wc / ".git").exists():
        if wc.exists():
            shutil.rmtree(wc)
        wc.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", str(bare), str(wc)],
            check=True,
            capture_output=True,
        )
        # seed an initial commit so HEAD exists
        gitkeep = wc / ".gitkeep"
        gitkeep.write_text("")
        _run(["add", ".gitkeep"], cwd=wc)
        _run(["-c", "user.email=ttt@local", "-c", "user.name=ttt", "commit", "-m", "init"], cwd=wc)
        _run(["push", "origin", "main"], cwd=wc)


def _project_dir(project_id: UUID) -> Path:
    d = _wc() / str(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _page_file(project_id: UUID, page_path: str) -> Path:
    safe = _safe_page_path(page_path)
    target = _project_dir(project_id) / safe
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


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


def write_pages(
    project_id: UUID,
    pages: dict[str, str],
    *,
    message: str,
    author: str = "ttt",
) -> str:
    """Write multiple pages and produce a single commit. Returns commit sha.

    Allows empty commits so version bumps land even when no content changes.
    """
    wc = _wc()
    rels: list[str] = []
    for page_path, md in pages.items():
        target = _page_file(project_id, page_path)
        target.write_text(md)
        rels.append(str(target.relative_to(wc)))
    if rels:
        _run(["add", "--", *rels], cwd=wc)
    _run(
        [
            "-c", f"user.email={author}@ttt.local",
            "-c", f"user.name={author}",
            "commit", "--allow-empty", "-m", message,
        ],
        cwd=wc,
    )
    _run(["push", "origin", "main"], cwd=wc)
    return _run(["rev-parse", "HEAD"], cwd=wc)


def write_page(
    project_id: UUID,
    page_path: str,
    markdown: str,
    *,
    message: str,
    author: str = "ttt",
) -> str:
    """Single-page edit. Returns commit sha."""
    return write_pages(project_id, {page_path: markdown}, message=message, author=author)


def read_page(project_id: UUID, commit_sha: str, page_path: str) -> str:
    rel = f"{project_id}/{_safe_page_path(page_path)}"
    return _run(["show", f"{commit_sha}:{rel}"], cwd=_wc())


def list_pages(project_id: UUID, commit_sha: str) -> dict[str, str]:
    """Return all pages for a project at a given commit as `{relative_path: markdown}`."""
    prefix = f"{project_id}/"
    paths = _run(
        ["ls-tree", "-r", "--name-only", commit_sha, "--", prefix],
        cwd=_wc(),
    ).splitlines()
    pages: dict[str, str] = {}
    for full in paths:
        if not full.endswith(".md"):
            continue
        if not full.startswith(prefix):
            continue
        rel = full[len(prefix) :]
        pages[rel] = _run(["show", f"{commit_sha}:{full}"], cwd=_wc())
    return pages
