"""Page repo + schema integration tests.

These used to exercise the static fan-out ingest path (now removed). The
agent path runs a Claude Agent SDK loop and isn't mockable without a
non-trivial fake — so instead we exercise the storage / schema invariants
that the agent relies on, via direct `report_repo` calls.
"""

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import SQLModel, create_engine

from ttt.config import settings
from ttt.reports import repo as report_repo
from ttt.reports import schema


@pytest.fixture
def isolated_data(monkeypatch):
    """Per-test sandbox: temp sqlite db + temp wiki cache dir, both pointed at
    by both `settings` and the module-level `engine` used by the page store."""
    tmp = Path(tempfile.mkdtemp(prefix="ttt-test-"))
    monkeypatch.setattr(settings, "ttt_db_path", tmp / "ttt.db")
    monkeypatch.setattr(settings, "ttt_wiki_dir", tmp / "wiki")

    test_engine = create_engine(f"sqlite:///{tmp / 'ttt.db'}")
    SQLModel.metadata.create_all(test_engine)

    from ttt import db as db_mod
    monkeypatch.setattr(db_mod, "engine", test_engine)
    monkeypatch.setattr(report_repo, "engine", test_engine)

    report_repo.init_store()
    try:
        yield test_engine
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _write(project_id, path: str, kind: str, body: str = "body") -> None:
    spec = schema.PageSpec(path=path, kind=kind, title=path, order=0)
    md = schema.page_with_frontmatter(spec, body)
    report_repo.write_page(project_id, path, md, message="test", author="test")


def test_write_and_read_roundtrip(isolated_data) -> None:
    project_id = uuid4()
    _write(project_id, "overview.md", "dynamic", "hello")
    pages = report_repo.list_pages(project_id)
    assert "overview.md" in pages
    assert "hello" in pages["overview.md"]


def test_per_repo_subtree_persists(isolated_data) -> None:
    """Nested page paths under repos/<slug>/ persist correctly and the FS
    cache mirrors them at the right depth."""
    project_id = uuid4()
    _write(project_id, "overview.md", "dynamic", "top")
    _write(project_id, "repos/mycelium/overview.md", "dynamic", "repo")
    pages = report_repo.list_pages(project_id)
    assert "overview.md" in pages
    assert "repos/mycelium/overview.md" in pages

    pdir = settings.ttt_wiki_dir / str(project_id)
    assert (pdir / "overview.md").exists()
    assert (pdir / "repos" / "mycelium" / "overview.md").exists()


def test_history_returns_revisions_in_order(isolated_data) -> None:
    project_id = uuid4()
    _write(project_id, "overview.md", "dynamic", "v1")
    _write(project_id, "overview.md", "dynamic", "v2")
    history = report_repo.page_history(project_id, "overview.md")
    assert len(history) == 2


def test_kinds_from_pages_after_write(isolated_data) -> None:
    """Frontmatter is authoritative — kinds_from_pages reads what was
    written, regardless of path or any seed defaults."""
    project_id = uuid4()
    _write(project_id, "overview.md", "stable", "anchor")
    _write(project_id, "product.md", "dynamic", "rewritable")
    _write(project_id, "memory.md", "hidden", "secret")
    pages = report_repo.list_pages(project_id)
    kinds = schema.kinds_from_pages(pages)
    assert kinds["overview.md"] == "stable"
    assert kinds["product.md"] == "dynamic"
    assert kinds["memory.md"] == "hidden"
