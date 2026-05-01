"""Wiki page schema + frontmatter helpers.

A report version is a tree of markdown pages, addressable by path under
`<project_id>/`. Each page declares its `kind` (stable | dynamic) in YAML
frontmatter; stable pages are human-curated (and only written on greenfield),
dynamic pages are agent-rewritten every ingest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PageKind = Literal["stable", "dynamic", "hidden", "report"]


@dataclass(frozen=True)
class PageSpec:
    path: str
    kind: PageKind
    title: str
    order: int
    grounded_by: tuple[str, ...] = field(default_factory=tuple)


# Default page set seeded on greenfield. Order is sidebar order at the same
# depth; nesting is purely path-derived (`a/b.md` is a child of `a.md`).
DEFAULT_PAGES: tuple[PageSpec, ...] = (
    PageSpec("standup.md",        "report",  "The Standup",   -10, ("overview.md", "team.md", "glossary.md")),
    PageSpec("overview.md",      "stable",  "Overview",      0),
    PageSpec("team.md",           "stable",  "Team",          10),
    PageSpec("glossary.md",       "stable",  "Glossary",      20),
    PageSpec("architecture.md",   "stable",  "Architecture",  30),
    PageSpec("status.md",         "dynamic", "Status",        40, ("overview.md", "team.md", "glossary.md")),
    PageSpec("activity.md",       "dynamic", "Activity",      50, ("overview.md", "glossary.md")),
    PageSpec("conversations.md",  "dynamic", "Conversations", 60, ("overview.md", "team.md")),
)

# Pages that surface as their own UI element (rendered above the wiki, not in
# the sidebar tree). The sidebar tree should filter these out.
SURFACE_PATHS: frozenset[str] = frozenset({"standup.md"})

REQUIRED_PATHS: frozenset[str] = frozenset(p.path for p in DEFAULT_PAGES)
SPEC_BY_PATH: dict[str, PageSpec] = {p.path: p for p in DEFAULT_PAGES}

EMPTY_PAGE_PLACEHOLDER = "_(no content yet)_"


def stable_paths() -> list[str]:
    return [p.path for p in DEFAULT_PAGES if p.kind == "stable"]


def dynamic_paths() -> list[str]:
    return [p.path for p in DEFAULT_PAGES if p.kind == "dynamic"]


def report_paths() -> list[str]:
    return [p.path for p in DEFAULT_PAGES if p.kind == "report"]


def validate_pages(pages: dict[str, str]) -> list[str]:
    """Return a list of missing required page paths. Empty list = valid."""
    return sorted(REQUIRED_PATHS - pages.keys())


# ---------- Frontmatter ----------

_FENCE = "---\n"


def parse_frontmatter(markdown: str) -> tuple[dict[str, object], str]:
    """Return ({key: value}, body). YAML-lite: only top-level scalar key:value pairs."""
    if not markdown.startswith(_FENCE):
        return {}, markdown
    end = markdown.find(f"\n{_FENCE}", len(_FENCE))
    if end == -1:
        return {}, markdown
    block = markdown[len(_FENCE) : end + 1]  # include trailing newline
    rest = markdown[end + len(_FENCE) + 1 :]
    fm: dict[str, object] = {}
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        k, _, v = raw.partition(":")
        fm[k.strip()] = _coerce(v.strip())
    return fm, rest


def serialize_frontmatter(fm: dict[str, object], body: str) -> str:
    if not fm:
        return body
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {_dump(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body.lstrip("\n")


def page_with_frontmatter(spec: PageSpec, body: str) -> str:
    fm: dict[str, object] = {
        "title": spec.title,
        "kind": spec.kind,
        "order": spec.order,
    }
    if spec.grounded_by:
        fm["grounded_by"] = list(spec.grounded_by)
    return serialize_frontmatter(fm, body)


def _coerce(v: str) -> object:
    s = v.strip()
    if not s:
        return ""
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [x.strip().strip("'\"") for x in inner.split(",")]
    if s.lower() in {"true", "false"}:
        return s.lower() == "true"
    if s.lstrip("-").isdigit():
        return int(s)
    return s.strip("'\"")


def _dump(v: object) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


# ---------- Page tree (for sidebar nav) ----------

@dataclass
class PageNode:
    path: str
    title: str
    kind: PageKind
    order: int
    children: list["PageNode"] = field(default_factory=list)


def build_tree(pages: dict[str, str]) -> list[PageNode]:
    """Build a hierarchical tree from `{path: markdown}`. Root pages have no parent.

    Pages in `SURFACE_PATHS` (e.g. `standup.md`) are excluded — they have their
    own UI surface above the wiki, not a sidebar entry.
    """
    nodes: dict[str, PageNode] = {}
    for path, md in pages.items():
        if path in SURFACE_PATHS:
            continue
        fm, _ = parse_frontmatter(md)
        spec = SPEC_BY_PATH.get(path)
        title = str(fm.get("title") or (spec.title if spec else _path_to_title(path)))
        kind: PageKind = (
            fm.get("kind") if fm.get("kind") in ("stable", "dynamic")  # type: ignore[assignment]
            else (spec.kind if spec else "stable")
        )
        raw_order = fm.get("order")
        order = raw_order if isinstance(raw_order, int) else (spec.order if spec else 999)
        nodes[path] = PageNode(path=path, title=title, kind=kind, order=order)

    roots: list[PageNode] = []
    for path, node in sorted(nodes.items(), key=lambda kv: (_depth(kv[0]), nodes[kv[0]].order, kv[0])):
        parent_path = _parent_path(path)
        if parent_path and parent_path in nodes:
            nodes[parent_path].children.append(node)
        else:
            roots.append(node)

    def _sort(node_list: list[PageNode]) -> None:
        node_list.sort(key=lambda n: (n.order, n.path))
        for n in node_list:
            _sort(n.children)
    _sort(roots)
    return roots


def _path_to_title(path: str) -> str:
    leaf = path.rsplit("/", 1)[-1].removesuffix(".md")
    return leaf.replace("-", " ").replace("_", " ").title()


def _parent_path(path: str) -> str | None:
    """`architecture/design.md` → `architecture.md`. Top-level → None."""
    if "/" not in path:
        return None
    parent_dir = path.rsplit("/", 1)[0]
    return f"{parent_dir}.md"


def _depth(path: str) -> int:
    return path.count("/")
