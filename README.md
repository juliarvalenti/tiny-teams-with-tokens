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

The agent receives the stable pages as context when rewriting dynamic pages. So "bumped litellm" gets filtered out unless an active goal mentions LLM cost; "v1.0.7rc1 released" survives if "ship v1.0" is in the goals. Signal becomes mechanical instead of vibes.

You edit any page in the browser (Milkdown WYSIWYG); page revisions are stored in SQLite.

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

State (SQLite + wiki cache) persists in a named volume (`ttt-data`). To wipe: `docker compose down -v`.

## Quickstart (local dev)

Requirements: Python 3.12+, [uv](https://github.com/astral-sh/uv), Node 20+, npm.

```bash
# 1. clone + install
git clone https://github.com/juliarvalenti/tiny-teams-with-tokens
cd tiny-teams-with-tokens

# 2. environment
cp .env.example .env
# add ANTHROPIC_API_KEY to .env
# (optional) add GITHUB_TOKEN for higher rate limits

# 3. start everything
bash up.sh
# backend  → http://localhost:8765
# frontend → http://localhost:3001
```

`up.sh` installs deps, initializes the DB if missing, and starts both servers with hot reload.

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
    ├── api/
    │   ├── projects.py      CRUD + ingest trigger + cancel
    │   ├── chat.py          SSE chat endpoint
    │   ├── reports.py       page read/write
    │   ├── workspace.py     per-page workspace ops
    │   └── mcp_server.py    MCP tools (ttt_list_projects, ttt_ask)
    ├── pipeline/
    │   ├── agent_core.py    shared agent factory + persist hook
    │   ├── agent_ingestor.py  ingest agent: system prompt, log streaming
    │   └── mcp_github.py    in-process GitHub MCP (wraps httpx connector)
    ├── chat/
    │   └── agent.py         chat agent: system prompt, SSE event translation
    ├── reports/
    │   ├── repo.py          sqlite page store + FS cache mirror
    │   └── schema.py        page kinds, frontmatter, sidebar tree
    ├── models.py            Project, Report, IngestRun, ChatSession
    └── cli.py               `ttt init-data`

frontend/
├── app/
│   ├── page.tsx             project list / home
│   └── projects/[id]/       wiki: sidebar + editor + chat panel
└── components/
    ├── IngestLogStream.tsx  live ingest log (SSE)
    └── ProjectCard.tsx      card with age, delete

data/                        gitignored — sqlite DB + wiki FS cache
```

Pages live in the `pagerevision` table — one row per save. The current state of any page is the latest revision; history is a `SELECT … ORDER BY created_at DESC`. A filesystem cache at `data/wiki/<project_id>/` mirrors current pages so the agent's Read/Edit/Write tools operate on real files; sqlite is authoritative.

## MCP server

The wiki chat agent is exposed as an MCP server so other Claude Code sessions can query it directly.

**Tools:**
- `ttt_list_projects` — list all projects with id, name, and latest version
- `ttt_ask(project_id, question)` — ask the chat agent a question; returns the full response

**Setup:** `.mcp.json` is already committed. As long as the backend is running, Claude Code will connect automatically on session start.

```json
{
  "mcpServers": {
    "ttt": { "type": "http", "url": "http://localhost:8765/mcp" }
  }
}
```

## Run tests

```bash
uv run pytest -x -q
```

Tests force `ANTHROPIC_API_KEY=""` so the agents fall through to deterministic stubs — no API calls, no cost.

## What's stubbed / TODO

- **Confluence connector** — needs base URL + creds. Currently reads `backend/ttt/fixtures/confluence.md`.
- **Webex connector** — needs personal access token + channel access. Currently reads `backend/ttt/fixtures/webex.md`.
- **Citation links** — citations are markdown text right now (`[commit a1b2c3d]`); could resolve to clickable URLs.
- **Greenfield stable regen** — no "regenerate the anchor" button. Edit stable pages by hand or delete and reingest.

## Notes for sharing

- The Anthropic API key in `.env` is yours and is gitignored — it never leaves your machine.
- The lockfiles (`uv.lock`, `frontend/package-lock.json`) are committed; teammates should `uv sync` and `npm ci` to reproduce.
- Cost: a full ingest cycle on a small public repo runs the agent on Haiku. Pennies per ingest.

## License

Unlicensed PoC. Don't ship it to production without further hardening.
