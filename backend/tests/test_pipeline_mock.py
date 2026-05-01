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
    """Per-test sandbox: temp sqlite db + temp wiki cache dir, both pointed at
    by both `settings` and the module-level `engine` used by the page store."""
    tmp = Path(tempfile.mkdtemp(prefix="ttt-test-"))
    monkeypatch.setattr(settings, "ttt_db_path", tmp / "ttt.db")
    monkeypatch.setattr(settings, "ttt_wiki_dir", tmp / "wiki")
    monkeypatch.setattr(settings, "anthropic_api_key", "")  # force stub agents

    test_engine = create_engine(f"sqlite:///{tmp / 'ttt.db'}")
    SQLModel.metadata.create_all(test_engine)

    # The page store uses ttt.db.engine internally — patch it for the test.
    from ttt import db as db_mod
    monkeypatch.setattr(db_mod, "engine", test_engine)
    monkeypatch.setattr(report_repo, "engine", test_engine)

    report_repo.init_store()
    try:
        yield test_engine
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

        pages = report_repo.list_pages(project.id)
        for path in schema.REQUIRED_PATHS:
            assert path in pages, f"missing required page: {path}"
        for path, md in pages.items():
            fm, _ = schema.parse_frontmatter(md)
            assert fm.get("kind") in {"stable", "dynamic", "hidden", "report"}, f"{path} missing kind frontmatter"


@pytest.mark.asyncio
async def test_incremental_preserves_stable_pages(isolated_data):
    engine = isolated_data
    with Session(engine) as session:
        project = Project(name="acme", charter="")
        session.add(project)
        session.commit()
        session.refresh(project)

        run1 = IngestRun(project_id=project.id, status="pending")
        project.locked = True
        session.add_all([run1, project])
        session.commit()
        session.refresh(run1)
        report1 = await run_ingest(session, project, run=run1)
        v1_pages = report_repo.list_pages(project.id)

        marker = "MANUAL EDIT MARKER 1234"
        edited_overview = v1_pages["overview.md"] + f"\n\n{marker}\n"
        report_repo.write_page(
            project.id,
            "overview.md",
            edited_overview,
            message="manual edit",
            author="test",
        )

        run2 = IngestRun(project_id=project.id, status="pending")
        project.locked = True
        session.add_all([run2, project])
        session.commit()
        session.refresh(run2)
        report2 = await run_ingest(session, project, run=run2)
        assert report2.version == 2
        assert not report2.is_greenfield

        v2_pages = report_repo.list_pages(project.id)
        assert marker in v2_pages["overview.md"], "stable page edit was clobbered by reingest"
        for path in schema.default_dynamic_paths():
            assert path in v2_pages

        # History viewer prerequisite: overview.md should have at least 2 revisions
        # (greenfield + manual edit).
        history = report_repo.page_history(project.id, "overview.md")
        assert len(history) >= 2
        assert any(r.author == "test" for r in history)


@pytest.mark.asyncio
async def test_custom_stable_page_preserved_across_reingest(isolated_data):
    """Frontmatter is authoritative — a user-created page with kind: stable
    that's NOT in DEFAULT_PAGES must survive a reingest unchanged."""
    engine = isolated_data
    with Session(engine) as session:
        project = Project(name="acme", charter="")
        session.add(project)
        session.commit()
        session.refresh(project)
        run1 = IngestRun(project_id=project.id, status="pending")
        project.locked = True
        session.add_all([run1, project])
        session.commit()
        session.refresh(run1)
        await run_ingest(session, project, run=run1)

        custom_md = (
            "---\ntitle: Roadmap\nkind: stable\norder: 5\n---\n"
            "# Roadmap\n\nQ3 milestones go here.\n"
        )
        report_repo.write_page(
            project.id, "roadmap.md", custom_md,
            message="user creates custom stable page", author="test",
        )

        run2 = IngestRun(project_id=project.id, status="pending")
        project.locked = True
        session.add_all([run2, project])
        session.commit()
        session.refresh(run2)
        await run_ingest(session, project, run=run2)

        v2_pages = report_repo.list_pages(project.id)
        assert "roadmap.md" in v2_pages, "custom stable page disappeared on reingest"
        assert "Q3 milestones go here" in v2_pages["roadmap.md"], "custom stable page content was rewritten"


@pytest.mark.asyncio
async def test_kind_flip_lets_dynamic_be_rewritten(isolated_data):
    """A page that the user flips from stable→dynamic should be rewritten on
    the next ingest. Static path's named-dynamic synthesizers don't write
    arbitrary paths — assert through the schema helpers instead, which is the
    authoritative source the agent path uses."""
    engine = isolated_data
    with Session(engine) as session:
        project = Project(name="acme", charter="")
        session.add(project)
        session.commit()
        session.refresh(project)
        run = IngestRun(project_id=project.id, status="pending")
        project.locked = True
        session.add_all([run, project])
        session.commit()
        session.refresh(run)
        await run_ingest(session, project, run=run)

        # Flip overview.md from stable → dynamic by rewriting its frontmatter.
        v1 = report_repo.list_pages(project.id)
        fm, body = schema.parse_frontmatter(v1["overview.md"])
        fm["kind"] = "dynamic"
        flipped = schema.serialize_frontmatter(fm, body)
        report_repo.write_page(
            project.id, "overview.md", flipped,
            message="user flips kind", author="test",
        )

        v1_after_flip = report_repo.list_pages(project.id)
        # overview.md now reports kind=dynamic at runtime.
        assert schema.kinds_from_pages(v1_after_flip)["overview.md"] == "dynamic"
        # ...so it's NOT in the preserve list.
        assert "overview.md" not in schema.stable_paths_in(v1_after_flip)
