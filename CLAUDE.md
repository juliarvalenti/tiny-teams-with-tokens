# CLAUDE.md

Instructions for Claude Code (and other coding agents) working on this repo. Read [`PLAN.md`](./PLAN.md) for the full design rationale and what to build next.

## TL;DR

`tiny-teams-with-tokens` is a status-wiki-per-project tool. Reports are *trees of markdown pages* in a git repo, not single docs. Each page is either:

- **stable** — written on greenfield ingest, preserved across reingests, human-curated (the project's anchor: purpose, goals, glossary, architecture)
- **dynamic** — rewritten every ingest, grounded by the stable pages (status, activity, conversations)

The stable/dynamic split is the core architectural decision. Don't undo it without reading PLAN.md §6.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLModel + SQLite, `anthropic` SDK (Messages API).
- **Frontend**: Next.js 15 + React 19 + Tailwind + SWR + Milkdown Crepe (markdown WYSIWYG, markdown is the model).
- **Storage**: SQLite for everything. Page content lives in the `pagerevision` table (one row per save, latest-by-`created_at` is the current page). A filesystem cache at `data/wiki/<project_id>/` mirrors the current state so the chat agent's Read/Edit/Write tools operate on real files; sqlite is authoritative.
- **Package management**: `uv` for Python, `npm ci` for frontend. Versions pinned, `save-exact=true` in `frontend/.npmrc`.
- **LLM**: Haiku for everything in PoC (~7 calls per ingest, pennies). Configurable in `backend/ttt/config.py`.

## Common commands

```bash
# Backend
uv sync --group dev                                       # install
uv run pytest -x -q                                       # tests (forced stub mode, no API calls)
uv run ttt init-data                                      # create local sqlite + git report repo
uv run uvicorn ttt.main:app --port 8765                   # dev server

# Frontend
cd frontend && npm ci                                     # install
cd frontend && npm run dev -- -p 3001                     # dev server
cd frontend && npm run build                              # production build (only for docker prod path)

# Docker
docker compose up --build                                 # backend + frontend, persistent volume

# Linting (configured but not in CI)
uv run ruff check .
uv run ruff format .
```

## Where to start reading the code

In this order:

1. `backend/ttt/pipeline/runner.py` — the orchestrator. Spine of the project.
2. `backend/ttt/reports/schema.py` — page kinds, frontmatter, validation, sidebar tree.
3. `backend/ttt/pipeline/page_synthesizers/founding.py` — what the anchor *is*.
4. `backend/ttt/pipeline/page_synthesizers/status.py` — example dynamic page synthesizer.
5. `backend/ttt/pipeline/connectors/github.py` — the only real connector. Copy this shape for Confluence/Webex.
6. `frontend/app/projects/[id]/page.tsx` — the wiki UI.

## Conventions worth respecting

### Code

- **Modern Python**: type hints, `X | Y` unions, `async/await` everywhere. `dataclasses` for value objects, `pydantic` for API schemas.
- **No comments unless they explain WHY** something non-obvious is being done. Don't restate what the code does.
- **No emojis** in code or commit messages.
- **No README/docs files** unless explicitly requested. (`PLAN.md` and this file are explicit asks.)
- **Frontend**: client components for anything that mounts editors / uses SWR. App Router, no Pages Router.

### Pipeline / agents

- Stub fallbacks everywhere. Every synthesizer/extractor checks `anthropic_client.is_available()` and falls through to a deterministic stub if no key. Tests force `ANTHROPIC_API_KEY=""` to use stubs.
- **Connectors are independently failable.** A failed connector becomes `_(source: skipped (...) )_` in the deltas. Never abort the whole ingest because one source died.
- **Citations are required on dynamic pages.** Stable pages don't carry citations.
- **Synthesizer prompts must enforce "no preamble, output markdown only".** Every prompt currently does. Don't break this.
- **Stable pages are written ONLY on greenfield ingest.** Incremental ingest reads existing stable pages from prior commit, preserves them as-is. If you find yourself adding code that rewrites stable pages on incremental, you're probably wrong; check PLAN.md §6.2.

### Git / storage

- `data/` is gitignored — both the SQLite DB and the bare report repo are runtime artifacts.
- Each ingest produces ONE git commit on the report repo. Each human edit produces ONE commit. So `git log` is the audit trail.
- Use `--allow-empty` on commits — identical-content ingests still produce a versioned commit (we want the version bump).

### Secrets

- `ANTHROPIC_API_KEY` and connector tokens (`GITHUB_TOKEN`, `CONFLUENCE_*`, `WEBEX_TOKEN`) live in `.env`. **Never commit `.env`.** It's gitignored; keep it that way.
- The Webex token in particular must NEVER be logged. The `WebexConnector` has a comment to this effect; respect it.

## What to build next

See [`PLAN.md`](./PLAN.md) §8. Top of the list right now:

1. **In-app chat** with project-scoped tool use (read wiki + live GH/Confluence/Webex). Highest leverage — turns the wiki from one-way reading into queryable.
2. **Real Confluence connector** (M6) — blocked on creds.
3. **Real Webex connector** (M7) — blocked on personal token + channel access.
4. **MCP server** — exposing the wiki to other Claude Code sessions.

If you (the agent) are picking this up cold, follow the "How to pick this up cold" checklist at the bottom of PLAN.md.

## Don't

- Don't reintroduce git-backed page storage. We migrated to a `pagerevision` table — audit is `SELECT … ORDER BY created_at DESC` per page. The `data/wiki/` filesystem is a regenerable cache.
- Don't collapse the stable/dynamic split. PLAN.md §6.1 explains why.
- Don't add propose-diff / human-in-the-loop review machinery. PLAN.md §6.2 — auto-accept everywhere is a deliberate choice.
- Don't introduce a workflow framework (Airflow/Prefect/Celery). PLAN.md §6.7.
- Don't swap Crepe for Tiptap/BlockNote/Lexical-with-markdown-plugin. They lose markdown fidelity. PLAN.md §6.5.
- Don't write into `.env` as a tool call. If you need an API key, ask the user to add it themselves.
