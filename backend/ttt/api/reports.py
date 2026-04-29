from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ttt.db import get_session
from ttt.models import Project, Report
from ttt.reports import repo as report_repo
from ttt.reports import schema as report_schema

router = APIRouter(tags=["reports"])


class PageWrite(BaseModel):
    markdown: str
    author: str = "ttt-web"
    message: str | None = None


class PageCreate(BaseModel):
    path: str  # must end in .md
    title: str
    parent_path: str | None = None  # for hierarchical placement
    author: str = "ttt-web"


def _tree_to_dict(nodes: list[report_schema.PageNode]) -> list[dict[str, Any]]:
    return [
        {
            "path": n.path,
            "title": n.title,
            "kind": n.kind,
            "order": n.order,
            "children": _tree_to_dict(n.children),
        }
        for n in nodes
    ]


@router.get("/projects/{project_id}/reports")
def list_reports(project_id: UUID, session: Session = Depends(get_session)) -> list[Report]:
    return list(
        session.exec(
            select(Report)
            .where(Report.project_id == project_id)
            .order_by(Report.version.desc())
        ).all()
    )


@router.get("/projects/{project_id}/reports/{version}")
def get_report(
    project_id: UUID, version: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Return the report's metadata + page tree (paths only — call /pages/{path} for content)."""
    report = session.exec(
        select(Report).where(Report.project_id == project_id, Report.version == version)
    ).first()
    if not report:
        raise HTTPException(404, "report not found")
    pages = report_repo.list_pages(project_id, report.git_commit)
    tree = report_schema.build_tree(pages)
    return {
        **report.model_dump(),
        "page_tree": _tree_to_dict(tree),
    }


@router.get("/projects/{project_id}/reports/{version}/pages/{page_path:path}")
def get_page(
    project_id: UUID,
    version: int,
    page_path: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    report = session.exec(
        select(Report).where(Report.project_id == project_id, Report.version == version)
    ).first()
    if not report:
        raise HTTPException(404, "report not found")
    try:
        markdown = report_repo.read_page(project_id, report.git_commit, page_path)
    except Exception:
        raise HTTPException(404, f"page not found: {page_path}")
    fm, body = report_schema.parse_frontmatter(markdown)
    return {
        "path": page_path,
        "markdown": markdown,
        "frontmatter": fm,
        "body": body,
        "git_commit": report.git_commit,
    }


@router.put("/projects/{project_id}/reports/{version}/pages/{page_path:path}")
def put_page(
    project_id: UUID,
    version: int,
    page_path: str,
    body: PageWrite,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    if project.locked:
        raise HTTPException(409, "project is locked while ingest is running")

    report = session.exec(
        select(Report).where(Report.project_id == project_id, Report.version == version)
    ).first()
    if not report:
        raise HTTPException(404, "report not found")

    msg = body.message or f"edit {page_path} on v{version} by {body.author}"
    new_sha = report_repo.write_page(
        project_id,
        page_path,
        body.markdown,
        message=msg,
        author=body.author,
    )
    report.git_commit = new_sha
    session.add(report)
    session.commit()
    return {"git_commit": new_sha, "path": page_path}


@router.post("/projects/{project_id}/reports/{version}/pages")
def create_page(
    project_id: UUID,
    version: int,
    body: PageCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create a new (stable) page in the wiki. Used by the +new-page UI."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    if project.locked:
        raise HTTPException(409, "project is locked while ingest is running")
    report = session.exec(
        select(Report).where(Report.project_id == project_id, Report.version == version)
    ).first()
    if not report:
        raise HTTPException(404, "report not found")

    # Compute final path: nest under parent_path if provided.
    final_path = body.path
    if body.parent_path:
        parent_dir = body.parent_path.removesuffix(".md")
        if not final_path.startswith(parent_dir + "/"):
            final_path = f"{parent_dir}/{body.path.lstrip('/')}"
    if not final_path.endswith(".md"):
        final_path = final_path + ".md"

    # Reject duplicates.
    existing = report_repo.list_pages(project_id, report.git_commit)
    if final_path in existing:
        raise HTTPException(409, f"page already exists: {final_path}")

    fm = {"title": body.title, "kind": "stable", "order": 999}
    initial = report_schema.serialize_frontmatter(
        fm,
        f"# {body.title}\n\n{report_schema.EMPTY_PAGE_PLACEHOLDER}\n",
    )
    new_sha = report_repo.write_page(
        project_id,
        final_path,
        initial,
        message=f"create page {final_path} by {body.author}",
        author=body.author,
    )
    report.git_commit = new_sha
    session.add(report)
    session.commit()
    return {"git_commit": new_sha, "path": final_path, "title": body.title}
