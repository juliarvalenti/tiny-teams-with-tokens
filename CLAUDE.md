# CLAUDE.md

Instructions for Claude Code (and other coding agents) working on this repo. Read [`PLAN.md`](./PLAN.md) for the full design rationale and what to build next.

## TL;DR

`tiny-teams-with-tokens` is a status-wiki-per-project tool. Each project's wiki is a tree of markdown pages stored in sqlite, displayed via a Next.js UI, with two AI surfaces operating on it:

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

- **Backend**: Python 3.12, FastAPI, SQLModel + SQLite, `claude-agent-sdk` for the agents, `anthropic` SDK for the static fan-out fallback.
- **Frontend**: Next.js 15 + React 19 + Tailwind + SWR + Milkdown Crepe (markdown WYSIWYG, markdown is the model) + shadcn/ui (Tooltip, Dialog, Sheet, Popover, Button, Badge, ToggleGroup).
- **Storage**: SQLite for everything. Page content lives in the `pagerevision` table (one row per save, latest-by-`created_at` is the current page). A filesystem cache at `data/wiki/<project_id>/` mirrors the current state so the agents' Read/Edit/Write tools operate on real files; sqlite is authoritative.
- **GitHub access**: in-process MCP server (`pipeline/mcp_github.py`) wrapping our existing httpx-based GitHub connector. Both agents see it as `mcp__github__*` tools.
- **Package management**: `uv` for Python, `npm ci` for frontend. Versions pinned, `save-exact=true` in `frontend/.npmrc`.
- **LLM**: ingest uses Haiku (cost-conscious); chat uses Sonnet (better tool-use reasoning). Configurable in `backend/ttt/pipeline/agent_ingestor.py` and `backend/ttt/chat/agent.py`.

## Ingest paths

There are two backends for the Reingest button, gated by `INGEST_MODE`:

- `INGEST_MODE=agent` (active path) — the Claude Agent SDK loop in `pipeline/agent_ingestor.py`. The agent reads the wiki, calls GitHub MCP tools, writes pages directly. Frontmatter is the source of truth for which pages to preserve / rewrite.
- `INGEST_MODE=static` (default for tests, fallback) — the legacy fan-out in `pipeline/runner.py` (extractors + page synthesizers). Kept around for stub-mode tests and as a safety net. Will likely be removed once we trust the agent path.

## Common commands

```bash
# Backend
uv sync --group dev                                       # install
uv run pytest -x -q                                       # tests (forced stub mode, no API calls)
uv run ttt init-data                                      # create local sqlite + data/wiki/

# Dev server (hot reload)
INGEST_MODE=agent uv run uvicorn ttt.main:app --port 8765 \
    --reload --reload-dir backend/ttt

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

1. `backend/ttt/pipeline/agent_core.py` — the shared agent factory + persist hook. Spine of both agent surfaces.
2. `backend/ttt/pipeline/agent_ingestor.py` — the ingest agent: system prompt, log streaming, Report row creation.
3. `backend/ttt/chat/agent.py` — the chat agent: system prompt, SSE event translation.
4. `backend/ttt/pipeline/mcp_github.py` — in-process GitHub MCP. `@tool` decorators wrap our httpx connector.
5. `backend/ttt/reports/schema.py` — page kinds, frontmatter, runtime kind discovery (`kinds_from_pages`, `stable_paths_in`).
6. `backend/ttt/reports/repo.py` — sqlite-backed page store. `write_page` is the single write path; FS cache is mirrored automatically.
7. `backend/ttt/pipeline/runner.py` — the static fan-out fallback. Read after the agent path so you know what the agent path replaced.
8. `frontend/app/projects/[id]/page.tsx` — the wiki UI: 3-col layout, sidebar / editor / chat. Spawns `IngestLogStream` while locked.

## Conventions worth respecting

### Code

- **Modern Python**: type hints, `X | Y` unions, `async/await` everywhere. `dataclasses` for value objects, `pydantic` for API schemas.
- **No comments unless they explain WHY** something non-obvious is being done. Don't restate what the code does.
- **No emojis** in code or commit messages.
- **Frontend**: client components for anything that mounts editors / uses SWR. App Router, no Pages Router. shadcn primitives wrapped in domain components (e.g. `KindBadge` wraps `Badge` + `Tooltip`).

### Pipeline / agents

- **Frontmatter is authoritative.** When deciding "preserve or rewrite this page," read the file's `kind` frontmatter — never trust the path. `kinds_from_pages()` and `stable_paths_in()` are the runtime helpers; `default_*_paths()` are *seed-only* and should not be used for runtime decisions.
- **Both agents share `agent_core.build_agent_options()`.** Differences between chat and ingest are: system prompt, model, max_turns, persistence target (chat = untagged revisions, ingest = revisions tagged with `report_id`). Add new tools to `agent_core` so both surfaces get them.
- **Stub fallbacks everywhere in the static path.** Every synthesizer/extractor checks `anthropic_client.is_available()` and falls through to a deterministic stub if no key. Tests force `ANTHROPIC_API_KEY=""` to use stubs.
- **Connectors are independently failable** (in the static path). A failed connector becomes `_(source: skipped (...))_` in the deltas. Never abort the whole ingest because one source died.
- **Synthesizer prompts must enforce "no preamble, output markdown only".** Every prompt currently does. Don't break this.
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

**MCP server (M8) — shipped.** The wiki chat agent is exposed as an MCP server at `/mcp` on the FastAPI app. Register it in `.mcp.json` (already committed). Two tools: `ttt_list_projects` and `ttt_ask`. Uses Streamable HTTP transport (not SSE) — FastMCP's `streamable_http_app()` mounted at `/` with `mcp.session_manager.run()` inside the FastAPI lifespan.

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
