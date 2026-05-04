"""Wiki page schema + frontmatter helpers.

A report version is a tree of markdown pages, addressable by path under
`<project_id>/`. Each page declares its `kind` (stable | dynamic) in YAML
frontmatter; stable pages are human-curated (and only written on greenfield),
dynamic pages are agent-rewritten every ingest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, cast, get_args

PageKind = Literal["stable", "dynamic", "hidden", "report"]
_PAGE_KINDS: tuple[str, ...] = get_args(PageKind)


@dataclass(frozen=True)
class PageSpec:
    path: str
    kind: PageKind
    title: str
    order: int
    grounded_by: tuple[str, ...] = field(default_factory=tuple)


# Top-level seed pages for a Project — these describe the strategic effort
# as a whole, cross-cutting across all attached Repos / WebexRooms /
# ConfluenceSpaces. Per-source detail lives under `repos/<slug>/...`,
# `webex/<slug>/...`, `confluence/<slug>/...` (see templates below).
#
# Order is sidebar order at the same depth; nesting is path-derived
# (`a/b.md` is a child of `a.md`). All seed pages start `dynamic`; users can
# pin one as `stable` post-hoc via the kind toggle.
DEFAULT_PAGES: tuple[PageSpec, ...] = (
    PageSpec("standup.md",        "report",  "The Standup",   -10, ("overview.md",)),
    PageSpec("overview.md",       "dynamic", "Overview",        0),
    PageSpec("product.md",        "dynamic", "Product",        10),
    PageSpec("architecture.md",   "dynamic", "Architecture",   20),
    PageSpec("marketing.md",      "dynamic", "Marketing",      30),
    PageSpec("conversations.md",  "dynamic", "Conversations",  40, ("overview.md",)),
    PageSpec("memory.md",         "hidden",  "Memory",        100),
)


# Per-source page templates. Materialized into actual page paths by the
# ingest agent — e.g. for a Repo with slug `mycelium`, REPO_TEMPLATE expands
# into pages at `repos/mycelium/overview.md`, `repos/mycelium/team.md`, etc.
#
# Templates are intentionally minimal at first; we'll grow them once we have
# a feel for what's useful per-source.

REPO_TEMPLATE: tuple[PageSpec, ...] = (
    PageSpec("overview.md",       "dynamic", "Overview",        0),
    PageSpec("team.md",           "dynamic", "Team",           10),
    PageSpec("glossary.md",       "dynamic", "Glossary",       20),
    PageSpec("architecture.md",   "dynamic", "Architecture",   30),
    PageSpec("status.md",         "dynamic", "Status",         40),
    PageSpec("activity.md",       "dynamic", "Activity",       50),
    PageSpec("conversations.md",  "dynamic", "Conversations",  60),
)

WEBEX_TEMPLATE: tuple[PageSpec, ...] = (
    PageSpec("overview.md",       "dynamic", "Overview",        0),
    PageSpec("activity.md",       "dynamic", "Activity",       10),
)

CONFLUENCE_TEMPLATE: tuple[PageSpec, ...] = (
    PageSpec("overview.md",       "dynamic", "Overview",        0),
)


def expand_template(prefix: str, template: tuple[PageSpec, ...]) -> tuple[PageSpec, ...]:
    """Materialize a per-source template under `<prefix>/`. Used to build the
    full page enumeration shown to the ingest agent."""
    return tuple(
        PageSpec(
            path=f"{prefix}/{spec.path}",
            kind=spec.kind,
            title=spec.title,
            order=spec.order,
            grounded_by=spec.grounded_by,
        )
        for spec in template
    )


# Seed body for hidden memory pages. Static: not LLM-generated. The agent
# can append to it on subsequent ingests / chats to accumulate cross-ingest
# context the user shouldn't see in the wiki.
MEMORY_SEED = """# Memory

_Agent-only notes. Hidden from the wiki by default. Toggle via the eye icon at the bottom of the sidebar to see / edit. The agent reads this on every ingest and may append observations it wants to remember._

## Notes
- _(none yet — populated as the agent works)_
"""

# Pages that surface as their own UI element (rendered above the wiki, not in
# the sidebar tree). The sidebar tree should filter these out.
SURFACE_PATHS: frozenset[str] = frozenset({"standup.md"})

REQUIRED_PATHS: frozenset[str] = frozenset(p.path for p in DEFAULT_PAGES)
SPEC_BY_PATH: dict[str, PageSpec] = {p.path: p for p in DEFAULT_PAGES}

EMPTY_PAGE_PLACEHOLDER = "_(no content yet)_"


# ---------- Default-list helpers (seed-only) ----------
#
# These iterate DEFAULT_PAGES — the *seed* list written on greenfield. They
# are NOT authoritative at runtime: a user can create custom pages and flip
# kinds via the UI, after which the file's YAML frontmatter is the source of
# truth. Code that decides "what to preserve / rewrite on incremental" must
# call `kinds_from_pages(prior_pages)`, not these.


def default_stable_paths() -> list[str]:
    return [p.path for p in DEFAULT_PAGES if p.kind == "stable"]


def default_dynamic_paths() -> list[str]:
    return [p.path for p in DEFAULT_PAGES if p.kind == "dynamic"]


def default_report_paths() -> list[str]:
    return [p.path for p in DEFAULT_PAGES if p.kind == "report"]


def default_hidden_paths() -> list[str]:
    return [p.path for p in DEFAULT_PAGES if p.kind == "hidden"]


# Pages the founding synthesizer is responsible for filling in on greenfield
# (overview / team / glossary / architecture). These were the original
# "stable" set; they're now kind=dynamic by default but the static path's
# greenfield still routes them through the founding synthesizer because that
# prompt knows how to derive identity content from raw deltas.
FOUNDING_PATHS: tuple[str, ...] = (
    "overview.md",
    "team.md",
    "glossary.md",
    "architecture.md",
)


def validate_pages(pages: dict[str, str]) -> list[str]:
    """Return a list of missing required page paths. Empty list = valid."""
    return sorted(REQUIRED_PATHS - pages.keys())


# ---------- Runtime kind discovery (frontmatter is authoritative) ----------


def kinds_from_pages(pages: dict[str, str]) -> dict[str, PageKind]:
    """Read each page's frontmatter `kind` field; default to 'stable' when
    the page lacks frontmatter or has an unknown kind."""
    out: dict[str, PageKind] = {}
    for path, md in pages.items():
        fm, _ = parse_frontmatter(md)
        raw = str(fm.get("kind") or "").lower()
        if raw in _PAGE_KINDS:
            out[path] = cast(PageKind, raw)
        else:
            out[path] = "stable"
    return out


def paths_with_kind(pages: dict[str, str], kind: PageKind) -> list[str]:
    return [p for p, k in kinds_from_pages(pages).items() if k == kind]


def stable_paths_in(pages: dict[str, str]) -> list[str]:
    """Paths in `pages` whose frontmatter says they're stable (or hidden —
    same preserve-on-incremental semantics). Authoritative for runtime."""
    kinds = kinds_from_pages(pages)
    return [p for p, k in kinds.items() if k in ("stable", "hidden")]


def _kind_from_md(md: str) -> str:
    fm, _ = parse_frontmatter(md)
    return str(fm.get("kind") or "stable").lower()


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

    `kind: report` pages (e.g. `standup.md`) are excluded — they have their own
    UI surface, not a sidebar entry. `kind: hidden` pages ARE included; the
    frontend chooses whether to render them (cmd-shift-. style toggle).
    """
    nodes: dict[str, PageNode] = {}
    for path, md in pages.items():
        fm_kind = _kind_from_md(md)
        if fm_kind == "report":
            continue
        if path in SURFACE_PATHS:
            continue
        fm, _ = parse_frontmatter(md)
        spec = SPEC_BY_PATH.get(path)
        title = str(fm.get("title") or (spec.title if spec else _path_to_title(path)))
        raw_kind = fm.get("kind")
        kind: PageKind = (
            cast(PageKind, raw_kind)
            if raw_kind in _PAGE_KINDS
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
