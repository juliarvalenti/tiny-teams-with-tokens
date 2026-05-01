# tiny teams with tokens

Status reports for engineering teams that move fast with AI agents — pulled from GitHub, Confluence, and Webex, synthesized by Claude, persisted as an editable wiki.

> **Status:** PoC. Real GitHub connector. Confluence + Webex connectors stubbed pending creds. Built one afternoon, expect rough edges.

## What's interesting about this

Most "AI status report" tools dump activity into a doc and dress it in leadership grammar. The output reads as motion without meaning ("rapid iteration signaling stability work"). That's because there's nothing to *measure* the activity against.

TTT splits each project into two kinds of pages:

| Kind | Lifecycle | Purpose |
|---|---|---|
| **stable** | Written on greenfield ingest. Human-curated thereafter. Preserved across reingests. | The anchor: project purpose, active goals, glossary, architecture. |
| **dynamic** | Rewritten on every reingest. Grounded by the stable pages. | Status, activity, conversations — measured against the stable goals. |

The dynamic pages' synthesizers receive the stable pages as context. So "bumped litellm" gets filtered out unless an active goal mentions LLM cost; "v1.0.7rc1 released" survives if "ship v1.0" is in the goals. Signal becomes mechanical instead of vibes.

You edit any page in the browser (Milkdown WYSIWYG); commits land in a local bare git repo.

## Quickstart (Docker, prebuilt images from GHCR)

Requirements: Docker + Docker Compose v2.

```bash
git clone https://github.com/juliarvalenti/tiny-teams-with-tokens
cd tiny-teams-with-tokens
cp .env.example .env
# add ANTHROPIC_API_KEY to .env (and GITHUB_TOKEN for higher GH rate limits)

docker compose pull && docker compose up
# backend  → http://localhost:8765
# frontend → http://localhost:3000
```

Images are published on every push to `main` to `ghcr.io/juliarvalenti/tiny-teams-with-tokens-{backend,frontend}`. To pin a specific tag, set `TTT_IMAGE_TAG=sha-<short-sha>` in `.env`.

To build locally instead of pulling: `docker compose build && docker compose up`.

State (SQLite + report git repo) persists in a named volume (`ttt-data`). To wipe: `docker compose down -v`.

## Quickstart (local dev)

Requirements: Python 3.12+, [uv](https://github.com/astral-sh/uv), Node 20+, npm.

```bash
# 1. clone + install
git clone https://github.com/juliarvalenti/tiny-teams-with-tokens
cd tiny-teams-with-tokens
uv sync --group dev
(cd frontend && npm ci)

# 2. environment
cp .env.example .env
# add ANTHROPIC_API_KEY to .env
# (optional) add GITHUB_TOKEN for higher rate limits on the GitHub connector

# 3. initialize local data (sqlite + bare git repo for reports)
uv run ttt init-data

# 4. boot
uv run uvicorn ttt.main:app --port 8765   # backend
(cd frontend && npm run dev -- -p 3001)   # frontend

# 5. open
open http://localhost:3001
```

Click **New project**, give it a name, paste a charter (one paragraph: what the project is and what leadership cares about), point it at a GitHub repo, hit Create. First ingest takes ~15s; the wiki appears.

## Trying it on a real repo

The most fun smoke test:

- Name: anything
- Charter: a sentence or two on what the team is trying to do
- Repos: `mycelium-io/mycelium` (or any public repo)
- Leave Confluence / Webex empty (they fall back to mock fixtures)

When the wiki renders, open `overview.md` first — that's the agent's read on what the project is and its current goals. Then `status.md` will read very differently than a generic AI summary because it's measuring activity against those goals.

If the agent gets jargon wrong (it will — commit messages lie sometimes), edit `glossary.md`, save, reingest. Future syntheses will respect the correction because glossary is in the grounded context for every dynamic page.

## How it's wired

```
backend/
└── ttt/
    ├── api/                 FastAPI routers (projects, reports/wiki pages)
    ├── reports/
    │   ├── repo.py          git ops (multi-file commits, page reads)
    │   └── schema.py        page kinds, frontmatter, validation, sidebar tree
    ├── pipeline/
    │   ├── runner.py        greenfield vs incremental orchestration
    │   ├── extractors.py    per-source distillation (Haiku)
    │   ├── connectors/      github (real, httpx) | confluence/webex (stubs)
    │   ├── page_synthesizers/
    │   │   ├── founding.py       writes the 4 stable pages on greenfield
    │   │   ├── status.py         dynamic, grounded by overview/team/glossary
    │   │   ├── activity.py       dynamic, grounded by overview/glossary
    │   │   └── conversations.py  dynamic, grounded by overview/team
    │   └── anthropic_client.py   thin wrapper, retry/backoff
    ├── models.py            Project, Report, IngestRun
    └── cli.py               `ttt init-data`

frontend/
├── app/                     Next.js App Router pages
└── components/
    ├── WikiSidebar.tsx      path-derived tree, +new-page, kind badges
    ├── ReportEditor.tsx     SWR-fetched page + Crepe edit/save
    └── CrepeEditor.tsx      thin Milkdown wrapper

data/                        gitignored — local sqlite + filesystem cache
```

Pages live in the `pagerevision` table — one row per save. The current state of any page is the latest revision; history is a query. A filesystem cache at `data/wiki/<project_id>/` mirrors the current pages so the chat agent's Read/Edit/Write tools work on real files; sqlite is the source of truth and the FS is regenerable.

## Run tests

```bash
uv run pytest -x -q
```

Tests force `ANTHROPIC_API_KEY=""` so the synthesizers fall through to deterministic stubs — they don't hit the real API and don't cost anything. Real-agent verification is manual via the UI.

## What's stubbed / TODO

- **Confluence connector** — needs base URL + creds. Currently reads `backend/ttt/fixtures/confluence.md`.
- **Webex connector** — needs personal access token + channel access. Currently reads `backend/ttt/fixtures/webex.md`.
- **MCP server** — exposing the wiki to other Claude Code sessions. Standalone process, not yet built. See plan.
- **Citation links** — citations are markdown text right now (`[commit a1b2c3d]`); could resolve to clickable URLs once we have the canonical repo.
- **Greenfield-only stable regen** — there's currently no "regenerate the anchor" button. If you want to refresh stable pages, edit them by hand or delete and reingest.

## Notes for sharing

- The Anthropic API key in `.env` is yours and is gitignored — it never leaves your machine.
- The lockfiles (`uv.lock`, `frontend/package-lock.json`) are committed; teammates should `uv sync` and `npm ci` to reproduce.
- Cost: a full ingest cycle on a small public repo is roughly 7 LLM calls (3 extractors + founding + 3 dynamic page synthesizers), all on Haiku. Pennies per ingest.

## License

Unlicensed PoC. Don't ship it to production without further hardening.
