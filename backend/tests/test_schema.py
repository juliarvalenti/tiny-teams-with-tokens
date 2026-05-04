from ttt.reports import schema


def test_default_pages_have_required_kinds() -> None:
    paths = {p.path for p in schema.DEFAULT_PAGES}
    # Top-level cross-cutting pages — per-source detail lives under
    # `repos/<slug>/...` etc., materialized by expand_template.
    assert paths == {
        "overview.md",
        "product.md",
        "architecture.md",
        "marketing.md",
        "conversations.md",
        "standup.md",
        "memory.md",
    }
    assert set(schema.default_stable_paths()) == set()
    assert set(schema.default_report_paths()) == {"standup.md"}
    assert set(schema.default_hidden_paths()) == {"memory.md"}


def test_repo_template_expands_under_prefix() -> None:
    expanded = schema.expand_template("repos/mycelium", schema.REPO_TEMPLATE)
    paths = {s.path for s in expanded}
    assert "repos/mycelium/overview.md" in paths
    assert "repos/mycelium/team.md" in paths
    assert "repos/mycelium/conversations.md" in paths
    # Top-level overview is unchanged.
    assert "overview.md" not in paths


def test_webex_template_expands_with_minimal_pages() -> None:
    expanded = schema.expand_template(
        "webex/ioc-mycelium-sre", schema.WEBEX_TEMPLATE
    )
    paths = {s.path for s in expanded}
    assert paths == {
        "webex/ioc-mycelium-sre/overview.md",
        "webex/ioc-mycelium-sre/activity.md",
    }


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
        "product.md": "---\nkind: dynamic\n---\nbody",
        "memory.md": "---\nkind: hidden\n---\nbody",
    }
    preserve = set(schema.stable_paths_in(pages))
    assert preserve == {"overview.md", "roadmap.md", "memory.md"}


def test_validate_pages_returns_missing() -> None:
    pages = {"overview.md": "x", "product.md": "y"}
    missing = schema.validate_pages(pages)
    assert "architecture.md" in missing
    assert "marketing.md" in missing
    assert "conversations.md" in missing
    assert "memory.md" in missing
    assert "overview.md" not in missing


def test_frontmatter_roundtrip() -> None:
    spec = schema.SPEC_BY_PATH["product.md"]
    page = schema.page_with_frontmatter(spec, "## Roadmap\n\nQ3 milestones.\n")
    fm, body = schema.parse_frontmatter(page)
    assert fm["title"] == "Product"
    assert fm["kind"] == "dynamic"
    assert fm["order"] == 10
    assert "Q3 milestones" in body


def test_build_tree_handles_nesting() -> None:
    pages = {
        "overview.md": schema.page_with_frontmatter(schema.SPEC_BY_PATH["overview.md"], "x"),
        "architecture.md": schema.page_with_frontmatter(
            schema.SPEC_BY_PATH["architecture.md"], "x"
        ),
        "architecture/design.md": "---\ntitle: Design\nkind: stable\norder: 0\n---\nbody",
    }
    tree = schema.build_tree(pages)
    paths_at_root = [n.path for n in tree]
    assert "overview.md" in paths_at_root
    assert "architecture.md" in paths_at_root
    arch = next(n for n in tree if n.path == "architecture.md")
    assert any(c.path == "architecture/design.md" for c in arch.children)


def test_build_tree_handles_per_repo_subtree() -> None:
    """Per-source subtrees nest correctly: `repos/mycelium/overview.md` should
    appear under `repos/mycelium.md`. Without a parent `.md`, it's a root
    orphan — that's expected and not a bug."""
    pages = {
        "repos/mycelium.md": "---\ntitle: mycelium\nkind: dynamic\norder: 0\n---\nbody",
        "repos/mycelium/overview.md": (
            "---\ntitle: Overview\nkind: dynamic\norder: 0\n---\nbody"
        ),
    }
    tree = schema.build_tree(pages)
    by_path = {n.path: n for n in tree}
    assert "repos/mycelium.md" in by_path
    parent = by_path["repos/mycelium.md"]
    assert any(c.path == "repos/mycelium/overview.md" for c in parent.children)
