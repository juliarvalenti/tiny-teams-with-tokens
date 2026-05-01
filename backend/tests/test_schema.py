from ttt.reports import schema


def test_default_pages_have_required_kinds() -> None:
    paths = {p.path for p in schema.DEFAULT_PAGES}
    assert "overview.md" in paths
    assert "status.md" in paths
    assert set(schema.stable_paths()) == {"overview.md", "team.md", "glossary.md", "architecture.md"}
    assert set(schema.dynamic_paths()) == {"status.md", "activity.md", "conversations.md"}
    assert set(schema.report_paths()) == {"standup.md"}


def test_build_tree_excludes_surface_pages() -> None:
    pages = {
        "standup.md": "---\ntitle: Standup\nkind: dynamic\norder: -10\n---\nbody",
        "overview.md": "---\ntitle: Overview\nkind: stable\norder: 0\n---\nbody",
    }
    tree = schema.build_tree(pages)
    assert "standup.md" not in {n.path for n in tree}, "standup should not appear in sidebar"


def test_validate_pages_returns_missing() -> None:
    pages = {"overview.md": "x", "team.md": "y"}
    missing = schema.validate_pages(pages)
    assert "glossary.md" in missing
    assert "architecture.md" in missing
    assert "status.md" in missing
    assert "overview.md" not in missing


def test_frontmatter_roundtrip() -> None:
    spec = schema.SPEC_BY_PATH["status.md"]
    page = schema.page_with_frontmatter(spec, "## Status\n\nthings are fine.\n")
    fm, body = schema.parse_frontmatter(page)
    assert fm["title"] == "Status"
    assert fm["kind"] == "dynamic"
    assert fm["order"] == 40
    assert "things are fine" in body


def test_build_tree_handles_nesting() -> None:
    pages = {
        "overview.md": schema.page_with_frontmatter(schema.SPEC_BY_PATH["overview.md"], "x"),
        "architecture.md": schema.page_with_frontmatter(schema.SPEC_BY_PATH["architecture.md"], "x"),
        "architecture/design.md": "---\ntitle: Design\nkind: stable\norder: 0\n---\nbody",
    }
    tree = schema.build_tree(pages)
    paths_at_root = [n.path for n in tree]
    assert "overview.md" in paths_at_root
    assert "architecture.md" in paths_at_root
    arch = next(n for n in tree if n.path == "architecture.md")
    assert any(c.path == "architecture/design.md" for c in arch.children)
