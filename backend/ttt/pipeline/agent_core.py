"""Shared core for the chat agent and the ingest agent.

Both surfaces operate on the same project wiki with the same tools — only the
system prompt and the seed message differ. This module owns:

- The unified tool surface (wiki Read/Edit/Write/Glob/Grep + GitHub MCP +
  WebFetch + WebSearch).
- The PostToolUse hook that persists every Edit/Write to sqlite as a
  `PageRevision`, optionally tagged with a `report_id` (set for ingest
  agents, NULL for chat agents) and optionally calling an `on_write`
  callback (the ingest agent uses this to append a log line).
- A `build_agent_options()` factory each surface calls with its own prompt,
  model, and resume token.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

from ttt.config import settings
from ttt.pipeline.mcp_github import build_github_mcp
from ttt.pipeline.mcp_workspace import build_workspace_mcp
from ttt.reports import repo as report_repo

log = logging.getLogger("ttt.agent")

# Wiki I/O + the GitHub MCP toolset by name. Web tools also enabled for
# both surfaces — the ingest agent occasionally wants to peek at a release
# notes page or a docs URL beyond what the GH API exposes.
WIKI_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep"]
WEB_TOOLS = ["WebFetch", "WebSearch"]
GITHUB_MCP_TOOLS = [
    "mcp__github__github_list_commits",
    "mcp__github__github_list_releases",
    "mcp__github__github_list_issues",
    "mcp__github__github_get_issue",
    "mcp__github__github_list_pulls",
    "mcp__github__github_get_pr",
    "mcp__github__github_search_issues",
    "mcp__github__github_get_codeowners",
    "mcp__github__github_get_file",
    "mcp__github__github_list_dir",
    "mcp__github__github_get_readme",
]
WORKSPACE_MCP_TOOLS = [
    "mcp__workspace__workspace_get_relationships",
    "mcp__workspace__workspace_update_relationships",
]


def _normalize_repo_slug(repo: str) -> str | None:
    """`https://github.com/foo/bar.git` → `foo/bar`. None on garbage input."""
    s = repo.strip().rstrip("/")
    for prefix in ("https://github.com/", "github.com/"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    if s.endswith(".git"):
        s = s[: -len(".git")]
    parts = s.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}/{parts[1]}"


def build_citation_guidance(repos: list[str]) -> str:
    """Prompt fragment instructing the agent to emit cited items as proper
    markdown links so the wiki / chat renderer makes them clickable. Listed
    URL templates depend on the project's repos."""
    canonical = [r for r in (_normalize_repo_slug(r) for r in repos) if r]
    if not canonical:
        return (
            "CITATION FORMAT: When you cite a commit, issue, or PR, use a normal "
            "markdown link like `[commit `a1b2c3d`](URL)` so the renderer makes "
            "it clickable. If you don't know the canonical URL, leave the "
            "citation as plain text in brackets — the renderer has a fallback."
        )

    primary = canonical[0]
    examples = [
        f"`[commit `a1b2c3d`](https://github.com/{primary}/commit/a1b2c3d)`",
        f"`[issue #142](https://github.com/{primary}/issues/142)`",
        f"`[PR #99](https://github.com/{primary}/pull/99)`",
        "`[@alice](https://github.com/alice)` for people (or just write `@alice` — the renderer resolves it)",
    ]

    repo_list = "\n".join(f"  - https://github.com/{r}" for r in canonical)
    return (
        "CITATION FORMAT: When you cite something, use a markdown link so the "
        "renderer makes it clickable.\n\n"
        f"Project repos:\n{repo_list}\n\n"
        "Examples (use the repo the item lives in — don't guess across repos):\n"
        + "\n".join(f"  - {e}" for e in examples)
        + "\n\nIf you don't know the canonical URL for a citation, leave it as plain "
        "bracketed text (e.g. `[commit a1b2c3d]`) — there's a renderer-side "
        "fallback that resolves common patterns."
    )


def make_persist_hook(
    project_id: UUID,
    *,
    author: str,
    report_id: UUID | None,
    on_write: Callable[[str, int], None] | None = None,
):
    """Returns a PostToolUse hook that persists Edit/Write of files inside
    the project's wiki dir as a PageRevision via report_repo.write_page.

    `report_id` tags the revision with the ingest run's Report (None for chat
    edits). `on_write(page_path, byte_count)` runs after a successful persist
    — the ingest agent uses it to append a log line."""

    project_dir = (settings.ttt_wiki_dir / str(project_id)).resolve()

    async def persist(input_data, _tool_use_id, _context):
        tool_name = input_data.get("tool_name", "")
        if tool_name not in {"Edit", "Write"}:
            return {}
        tool_input = input_data.get("tool_input") or {}
        file_path = tool_input.get("file_path") or tool_input.get("path")
        if not file_path:
            return {}
        try:
            abs_path = Path(file_path).resolve()
            rel = abs_path.relative_to(project_dir)
        except (ValueError, OSError):
            return {}
        if not abs_path.exists():
            return {}
        try:
            content = abs_path.read_text()
            page_path = str(rel).replace("\\", "/")
            report_repo.write_page(
                project_id,
                page_path,
                content,
                message=f"{author}: {page_path}",
                author=author,
                report_id=report_id,
            )
            log.info("agent persisted %s (report_id=%s)", page_path, report_id)
            if on_write is not None:
                try:
                    on_write(page_path, len(content))
                except Exception:
                    log.exception("on_write callback raised; ignoring")
        except Exception:
            log.exception("agent persist failed for %s", file_path)
        return {}

    return persist


def build_agent_options(
    *,
    project_id: UUID,
    project_repos: list[str],
    system_prompt: str,
    model: str,
    max_turns: int,
    persist_author: str,
    report_id: UUID | None = None,
    resume: str | None = None,
    include_partial_messages: bool = False,
    on_write: Callable[[str, int], None] | None = None,
) -> ClaudeAgentOptions:
    """Compose ClaudeAgentOptions identically for chat and ingest, modulo a
    few caller-supplied knobs (prompt, model, max_turns, resume, run linkage)."""

    project_dir = settings.ttt_wiki_dir / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    # Make sure the FS cache reflects the latest sqlite state before the agent reads.
    report_repo.sync_to_disk(project_id)

    gh_server = build_github_mcp(project_repos, token=settings.github_token)
    workspace_server = build_workspace_mcp()

    return ClaudeAgentOptions(
        cwd=str(project_dir),
        allowed_tools=[*WIKI_TOOLS, *WEB_TOOLS, *GITHUB_MCP_TOOLS, *WORKSPACE_MCP_TOOLS],
        permission_mode="acceptEdits",
        system_prompt=system_prompt,
        model=model,
        resume=resume,
        setting_sources=[],
        mcp_servers={"github": gh_server, "workspace": workspace_server},
        env={
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
            "ANTHROPIC_API_KEY": settings.anthropic_api_key,
            **({"ANTHROPIC_BASE_URL": settings.anthropic_base_url} if settings.anthropic_base_url else {}),
        },
        debug_stderr=True,
        include_partial_messages=include_partial_messages,
        max_turns=max_turns,
        hooks={
            "PostToolUse": [
                HookMatcher(
                    matcher="Edit|Write",
                    hooks=[
                        make_persist_hook(
                            project_id,
                            author=persist_author,
                            report_id=report_id,
                            on_write=on_write,
                        )
                    ],
                )
            ],
        },
    )
