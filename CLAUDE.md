# CLAUDE.md

Instructions for Claude Code (and other coding agents) working on this repo. Read [`PLAN.md`](./PLAN.md) for the full design rationale and what to build next.

## TL;DR

`tiny-teams-with-tokens` is a status-wiki-per-project tool. A **Project** is a strategic effort that owns:

- **Repos** (GitHub repositories — first-class entities, not a JSON list)
- **WebexRooms** (chat sources — connector not yet wired)
- **ConfluenceSpaces** (doc sources — connector not yet wired)
- A wiki tree of markdown pages stored in sqlite

The wiki is two-level: cross-cutting top-level pages (`overview.md`, `product.md`, `architecture.md`, `marketing.md`, `conversations.md`, `standup.md`, `memory.md`) plus per-source subtrees (`repos/<slug>/...`, `webex/<slug>/...`, `confluence/<slug>/...`). Each Project also has `phase` (`prototype | venture | active | sunset`) and `cadence` (`weekly | monthly | quiet`) metadata for lifecycle / signal-from-noise.

Two AI surfaces operate on the wiki:

- **Ingest agent** — runs on demand (Reingest button); uses GitHub MCP + wiki tools to write/update pages.
- **Chat agent** — interactive side panel; same tool surface, ad-hoc questions and edits.

Both agents share `pipeline/agent_core.py`. Only the system prompt and seed message differ.

## Page kinds (frontmatter is authoritative)

Each page's YAML frontmatter declares its `kind`:

- **stable** — pinned by the user; agents preserve it across ingests.
- **dynamic** — agents rewrite it on every ingest, grounded by stable pages.
- **report** — special-rendered surface (currently just `standup.md`); rewritten every ingest, hidden from the wiki sidebar.
- **hidden** — agent-only memory (e.g. `memory.md`); read by the agents, hidden from the wiki sidebar by default (toggle to reveal).

**All seed pages currently default to `dynamic` on greenfield.** Users can pin a page as `stable` post-hoc via the kind toggle in the page header. The legacy "stable on greenfield only" semantics is gone — frontmatter is the runtime source of truth, not paths.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLModel + SQLite, `claude-agent-sdk` for the agents.
- **Frontend**: Next.js 15 + React 19 + Tailwind + SWR + Milkdown Crepe (markdown WYSIWYG, markdown is the model) + shadcn/ui (Tooltip, Dialog, Sheet, Popover, Button, Badge, ToggleGroup).
- **Storage**: SQLite for everything. Page content lives in the `pagerevision` table (one row per save, latest-by-`created_at` is the current page). A filesystem cache at `data/wiki/<project_id>/` mirrors the current state so the agents' Read/Edit/Write tools operate on real files; sqlite is authoritative.
- **GitHub access**: in-process MCP server (`pipeline/mcp_github.py`) wrapping our existing httpx-based GitHub connector. Both agents see it as `mcp__github__*` tools.
- **Package management**: `uv` for Python, `npm ci` for frontend. Versions pinned, `save-exact=true` in `frontend/.npmrc`.
- **LLM**: ingest uses Haiku (cost-conscious); chat uses Sonnet (better tool-use reasoning). Configurable in `backend/ttt/pipeline/agent_ingestor.py` and `backend/ttt/chat/agent.py`.

## Ingest path

A single Claude Agent SDK loop in `pipeline/agent_ingestor.py`. The agent reads the wiki on disk, calls GitHub MCP tools (scoped per-project to the attached Repos), and writes pages directly. Frontmatter is the source of truth for which pages to preserve / rewrite. The legacy static fan-out (extractors + per-source synthesizers + connectors/) was removed in #16.

To add a new source type (Webex, Confluence, …), build it as an in-process MCP server the agent can call (see `mcp_github.py` for the pattern) and attach it via the per-source schema (`Repo`, `WebexRoom`, `ConfluenceSpace`).

## Common commands

```bash
# Backend
uv sync --group dev                                       # install
uv run pytest -x -q                                       # tests (forced stub mode, no API calls)
uv run ttt init-data                                      # create local sqlite + data/wiki/

# Dev server (hot reload)
uv run uvicorn ttt.main:app --port 8765 --reload --reload-dir backend/ttt

# Frontend (hot reload by default)
cd frontend && npm ci                                     # install
cd frontend && npm run dev -- -p 3001                     # dev server
cd frontend && npm run build                              # production build (Docker prod path)

# Docker
docker compose up --build                                 # backend + frontend, persistent volume

# Linting (configured but not in CI)
uv run ruff check .
uv run ruff format .
```

## Where to start reading the code

In this order:

1. `backend/ttt/models.py` — Project, Repo, WebexRoom, ConfluenceSpace + the wiki-related rows (PageRevision, Report, IngestRun, ChatSession, ChatMessage). Reading this first explains the data shape every other module operates on.
2. `backend/ttt/services/projects.py` — schemas + business logic shared between the HTTP API and MCP server. `create_project_with_greenfield`, `add_repo`, `add_webex_room`, `add_confluence_space`, `start_ingest`, etc.
3. `backend/ttt/pipeline/agent_core.py` — the shared agent factory + persist hook. Spine of both agent surfaces.
4. `backend/ttt/pipeline/agent_ingestor.py` — the ingest agent: system prompt enumerates per-source page subtrees, log streaming, Report row creation.
5. `backend/ttt/chat/agent.py` — the chat agent: system prompt, SSE event translation.
6. `backend/ttt/pipeline/mcp_github.py` — in-process GitHub MCP scoped to the project's allowed repo URLs.
7. `backend/ttt/reports/schema.py` — `DEFAULT_PAGES` (top-level), `REPO_TEMPLATE` / `WEBEX_TEMPLATE` / `CONFLUENCE_TEMPLATE` (per-source), `expand_template`, page-kind helpers.
8. `backend/ttt/reports/repo.py` — sqlite-backed page store. `write_page` is the single write path; FS cache is mirrored automatically; `reconcile_from_disk` is the FS→sqlite safety net.
9. `backend/ttt/api/projects.py` + `backend/ttt/api/mcp_server.py` — thin shells over the service layer. Both surfaces bind to the same Pydantic schemas.
10. `frontend/app/projects/[id]/page.tsx` — the wiki UI: 3-col layout, sidebar / editor / chat. Spawns `IngestLogStream` while locked.

## Conventions worth respecting

### Code

- **Modern Python**: type hints, `X | Y` unions, `async/await` everywhere. `dataclasses` for value objects, `pydantic` for API schemas.
- **No comments unless they explain WHY** something non-obvious is being done. Don't restate what the code does.
- **No emojis** in code or commit messages.
- **Frontend**: client components for anything that mounts editors / uses SWR. App Router, no Pages Router. shadcn primitives wrapped in domain components (e.g. `KindBadge` wraps `Badge` + `Tooltip`).

### Pipeline / agents

- **Frontmatter is authoritative.** When deciding "preserve or rewrite this page," read the file's `kind` frontmatter — never trust the path. `kinds_from_pages()` and `stable_paths_in()` are the runtime helpers; `default_*_paths()` are *seed-only* and should not be used for runtime decisions.
- **Page tree is two-level.** Top-level pages (`DEFAULT_PAGES`) describe the Project as a whole; per-source detail goes under `repos/<slug>/...`, `webex/<slug>/...`, `confluence/<slug>/...`. The ingest agent's system prompt enumerates the exact paths to write — don't invent extra source folders. Use `report_schema.expand_template(prefix, template)` to materialize a per-source subtree.
- **Sources are first-class entities, not JSON arrays.** Repo / WebexRoom / ConfluenceSpace each have their own table, slug, and lifecycle. Don't reintroduce `repos: list[str]` on Project.
- **Both agents share `agent_core.build_agent_options()`.** Differences between chat and ingest are: system prompt, model, max_turns, persistence target (chat = untagged revisions, ingest = revisions tagged with `report_id`). Add new tools to `agent_core` so both surfaces get them.
- **HTTP API and MCP server share the service layer.** Both delegate to `services/projects.py`. New endpoints/tools should add a service helper first, then thin wrappers in both `api/projects.py` and `api/mcp_server.py`.
- **Bash is denied.** A `PreToolUse` hook in `agent_core` hard-rejects Bash / BashOutput / KillShell. The agent uses Edit/Write for files (so the persist hook records them) and the github MCP for code-level inspection.
- **Don't add propose-diff / human-in-the-loop review machinery.** Auto-accept everywhere. PLAN.md §6.2.
- **No RAG-style status pills, sentiment, or health scores.** PLAN.md §6.8 — explicit design stance.

### Storage

- `data/` is gitignored — sqlite DB and the wiki cache are runtime artifacts.
- The filesystem at `data/wiki/<project_id>/` is a regenerable mirror of sqlite (`report_repo.sync_to_disk(project_id)`). Don't write to it directly outside the persist hook.
- `IngestRun.log` stores the Docker-style live log line-by-line. Frontend polls `/api/ingest/{run_id}` while locked and renders it in `IngestLogStream`.
- Past ingests are auditable via the "Logs" button next to Reingest — `IngestHistoryPanel` lists every `IngestRun` with its full log.

### Secrets

- `ANTHROPIC_API_KEY` and connector tokens (`GITHUB_TOKEN`, `CONFLUENCE_*`, `WEBEX_TOKEN`) live in `.env`. **Never commit `.env`.** It's gitignored; keep it that way.
- The Webex token in particular must NEVER be logged. The `WebexConnector` has a comment to this effect; respect it.

## What to build next

See [`PLAN.md`](./PLAN.md) §8 and the open GitHub issues. Top of the list right now:

1. **Real Confluence connector** (M6) — blocked on creds.
2. **Real Webex connector** (M7) — blocked on personal token + channel access.
3. **Project interrelations + groups** (#9) → new home page (#3).
4. **Onboarding validation** (#14) — validate gh repos / confluence / webex during create.

**MCP server (M8) — shipped.** Public MCP surface mounted at `/mcp` on the FastAPI app via FastMCP's Streamable HTTP transport (not SSE — `streamable_http_app()` mounted at `/` with `mcp.session_manager.run()` inside the FastAPI lifespan). Tools: `ttt_list_projects`, `ttt_create_project`, `ttt_reingest`, `ttt_cancel_ingest`, `ttt_get_ingest_log`, `ttt_ask`, `ttt_list_repos`, `ttt_add_repo`, `ttt_list_webex_rooms`, `ttt_add_webex_room`, `ttt_list_confluence_spaces`, `ttt_add_confluence_space`. All bound to the same Pydantic schemas as the HTTP API via `services/projects.py`.

If you (the agent) are picking this up cold, follow the "How to pick this up cold" checklist at the bottom of PLAN.md.

## Don't

- Don't reintroduce git-backed page storage. We migrated to a `pagerevision` table — audit is `SELECT … ORDER BY created_at DESC` per page. The `data/wiki/` filesystem is a regenerable cache.
- Don't add a separate "stable runtime list" hardcoded by path. The four page kinds are declared in frontmatter; runtime decisions go through `schema.kinds_from_pages()` / `stable_paths_in()`.
- Don't add propose-diff / human-in-the-loop review machinery. PLAN.md §6.2 — auto-accept everywhere is a deliberate choice.
- Don't introduce a workflow framework (Airflow/Prefect/Celery). PLAN.md §6.7.
- Don't swap Crepe for Tiptap/BlockNote/Lexical-with-markdown-plugin. They lose markdown fidelity. PLAN.md §6.5.
- Don't add RAG status pills / sentiment indicators / health scores. PLAN.md §6.8.
- Don't write into `.env` as a tool call. If you need an API key, ask the user to add it themselves.
- Don't fork the agent surface — chat and ingest stay 99% the same. New tools / capabilities go in `agent_core`, not in one path or the other.
- Don't reintroduce `repos: list[str]` / `confluence_roots: list[str]` / `webex_channels: list[str]` JSON columns on Project. Sources are first-class: Repo, WebexRoom, ConfluenceSpace, each with their own table + slug + lifecycle.
- Don't reintroduce a static fan-out ingest path. The agent loop is the only path. Adding a new source type means adding an in-process MCP server (see `mcp_github.py`).
