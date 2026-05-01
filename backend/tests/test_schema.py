from ttt.reports import schema


def test_default_pages_have_required_kinds() -> None:
    paths = {p.path for p in schema.DEFAULT_PAGES}
    assert "overview.md" in paths
    assert "status.md" in paths
    # All seed pages default to dynamic — see schema.DEFAULT_PAGES rationale.
    assert set(schema.default_stable_paths()) == set()
    assert set(schema.default_dynamic_paths()) == {
        "overview.md", "team.md", "glossary.md", "architecture.md",
        "status.md", "activity.md", "conversations.md",
    }
    assert set(schema.default_report_paths()) == {"standup.md"}
    assert set(schema.default_hidden_paths()) == {"memory.md"}


def test_build_tree_excludes_surface_pages() -> None:
    pages = {
        "standup.md": "---\ntitle: Standup\nkind: report\norder: -10\n---\nbody",
        "overview.md": "---\ntitle: Overview\nkind: stable\norder: 0\n---\nbody",
    }
    tree = schema.build_tree(pages)
    assert "standup.md" not in {n.path for n in tree}, "standup should not appear in sidebar"


def test_build_tree_includes_hidden_pages_with_kind_marker() -> None:
    """Hidden pages stay in the tree response — the frontend filters them
    behind a cmd-shift-. style toggle. They're flagged via node.kind so the
    UI can distinguish."""
    pages = {
        "memory.md": "---\ntitle: Memory\nkind: hidden\norder: 0\n---\nsecret notes",
        "overview.md": "---\ntitle: Overview\nkind: stable\norder: 0\n---\nbody",
    }
    tree = schema.build_tree(pages)
    by_path = {n.path: n for n in tree}
    assert "memory.md" in by_path
    assert by_path["memory.md"].kind == "hidden"
    assert "overview.md" in by_path


def test_kinds_from_pages_reads_frontmatter() -> None:
    pages = {
        "overview.md": "---\nkind: stable\n---\nbody",
        "custom.md": "---\nkind: dynamic\n---\nbody",
        "memory.md": "---\nkind: hidden\n---\nbody",
        "loose.md": "no frontmatter",  # defaults to stable
    }
    kinds = schema.kinds_from_pages(pages)
    assert kinds["overview.md"] == "stable"
    assert kinds["custom.md"] == "dynamic"
    assert kinds["memory.md"] == "hidden"
    assert kinds["loose.md"] == "stable"


def test_stable_paths_in_uses_frontmatter_not_path() -> None:
    pages = {
        "overview.md": "---\nkind: stable\n---\nbody",
        # Custom page not in DEFAULT_PAGES but flagged stable should be preserved.
        "roadmap.md": "---\nkind: stable\n---\nbody",
        "status.md": "---\nkind: dynamic\n---\nbody",
        "memory.md": "---\nkind: hidden\n---\nbody",
    }
    preserve = set(schema.stable_paths_in(pages))
    assert preserve == {"overview.md", "roadmap.md", "memory.md"}


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
