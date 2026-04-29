import shutil
import tempfile
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from ttt.config import settings
from ttt.models import IngestRun, Project
from ttt.pipeline.runner import run_ingest
from ttt.reports import repo as report_repo
from ttt.reports import schema


@pytest.fixture
def isolated_data(monkeypatch):
    """Per-test sandbox so the real ./data tree is untouched."""
    tmp = Path(tempfile.mkdtemp(prefix="ttt-test-"))
    monkeypatch.setattr(settings, "ttt_db_path", tmp / "ttt.db")
    monkeypatch.setattr(settings, "ttt_report_repo", tmp / "reports.git")
    monkeypatch.setattr(settings, "ttt_report_worktree", tmp / "reports-wc")
    monkeypatch.setattr(settings, "anthropic_api_key", "")  # force stub agents
    report_repo.init_report_repo()
    engine = create_engine(f"sqlite:///{tmp / 'ttt.db'}")
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.asyncio
async def test_greenfield_writes_full_wiki(isolated_data):
    engine = isolated_data
    with Session(engine) as session:
        project = Project(name="payments-api", charter="Payments — high reliability.")
        session.add(project)
        session.commit()
        session.refresh(project)
        run = IngestRun(project_id=project.id, status="pending")
        project.locked = True
        session.add_all([run, project])
        session.commit()
        session.refresh(run)

        report = await run_ingest(session, project, run=run)
        assert report.version == 1
        assert report.is_greenfield

        pages = report_repo.list_pages(project.id, report.git_commit)
        # All required pages present
        for path in schema.REQUIRED_PATHS:
            assert path in pages, f"missing required page: {path}"
        # Each page has valid frontmatter declaring its kind
        for path, md in pages.items():
            fm, _ = schema.parse_frontmatter(md)
            assert fm.get("kind") in {"stable", "dynamic"}, f"{path} missing kind frontmatter"


@pytest.mark.asyncio
async def test_incremental_preserves_stable_pages(isolated_data):
    engine = isolated_data
    with Session(engine) as session:
        project = Project(name="acme", charter="")
        session.add(project)
        session.commit()
        session.refresh(project)

        # First ingest
        run1 = IngestRun(project_id=project.id, status="pending")
        project.locked = True
        session.add_all([run1, project])
        session.commit()
        session.refresh(run1)
        report1 = await run_ingest(session, project, run=run1)
        v1_pages = report_repo.list_pages(project.id, report1.git_commit)

        # Hand-edit a stable page through git so we can detect preservation
        marker = "MANUAL EDIT MARKER 1234"
        edited_overview = v1_pages["overview.md"] + f"\n\n{marker}\n"
        report_repo.write_page(
            project.id,
            "overview.md",
            edited_overview,
            message="manual edit",
            author="test",
        )

        # Second ingest — should preserve the manual marker on the stable page
        run2 = IngestRun(project_id=project.id, status="pending")
        project.locked = True
        session.add_all([run2, project])
        session.commit()
        session.refresh(run2)
        report2 = await run_ingest(session, project, run=run2)
        assert report2.version == 2
        assert not report2.is_greenfield

        v2_pages = report_repo.list_pages(project.id, report2.git_commit)
        assert marker in v2_pages["overview.md"], "stable page edit was clobbered by reingest"
        # Dynamic pages should still be regenerated (frontmatter present)
        for path in schema.dynamic_paths():
            assert path in v2_pages
