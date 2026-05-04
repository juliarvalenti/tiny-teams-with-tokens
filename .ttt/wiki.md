# tiny-teams-with-tokens

A status-wiki-per-project tool. Each project's wiki is a tree of markdown
pages stored in sqlite, served by a Next.js UI, with two AI surfaces
operating on it: an **ingest agent** (Reingest button) and a **chat agent**
(side panel). Both share the same tool surface and code path — only the
system prompt and seed message differ.

This file is the maintainer's steering hint to the ingest agent. It is not
the project charter, not the README, and not a substitute for reading the
actual code — it tells you where to look first.

## Read these first

The fastest path to "what does this project actually do":

- [CLAUDE.md](CLAUDE.md) — design rules and conventions for agents working
  on the codebase. Authoritative.
- [PLAN.md](PLAN.md) — the long-form design rationale, what's built, what's
  next.
- [README.md](README.md) — user-facing pitch + getting started.

## How the system is wired

The spine of both agent surfaces is shared:

- [backend/ttt/pipeline/agent_core.py](backend/ttt/pipeline/agent_core.py) —
  shared `build_agent_options()` factory + the persist hook that writes
  every Edit/Write into the `pagerevision` table.
- [backend/ttt/pipeline/agent_ingestor.py](backend/ttt/pipeline/agent_ingestor.py)
  — the ingest agent: system prompt, log streaming, Report row creation.
- [backend/ttt/chat/agent.py](backend/ttt/chat/agent.py) — the chat agent:
  system prompt + SSE event translation.
- [backend/ttt/pipeline/mcp_github.py](backend/ttt/pipeline/mcp_github.py) —
  in-process GitHub MCP server. Wraps our httpx connector as
  `mcp__github__*` tools. File-nav tools (`get_file`, `list_dir`,
  `get_readme`) are scoped through a per-project repo allowlist.
- [backend/ttt/pipeline/wiki_steering.py](backend/ttt/pipeline/wiki_steering.py)
  — fetches this very file and injects it into the ingest system prompt.

Page kinds (stable / dynamic / report / hidden) are declared in each page's
YAML frontmatter, not derived from path. The runtime helpers are in
[backend/ttt/reports/schema.py](backend/ttt/reports/schema.py) — see
`kinds_from_pages()` and `stable_paths_in()`.

The frontend wiki view that ties it all together:
[frontend/app/projects/[id]/page.tsx](frontend/app/projects/[id]/page.tsx).

## What to emphasize when documenting

- **Markdown is the model.** Crepe (a Milkdown WYSIWYG) edits markdown
  directly — there is no separate AST. Don't describe this as "rich text."
- **Sqlite is authoritative.** The filesystem at `data/wiki/<project_id>/`
  is a regenerable mirror so the agent's Read/Edit/Write tools have real
  files to operate on. Page revisions live in the `pagerevision` table.
- **Two ingest backends exist** but only one is real: `INGEST_MODE=agent`
  is the active path. The static fan-out (`INGEST_MODE=static`) is a
  fallback kept around for stub-mode tests; it will be removed.
- **Agents share `agent_core`.** New tools or capabilities go there, not
  into one surface. Don't document chat and ingest as having different
  toolsets — they don't.

## Things the agent would otherwise miss

- The MCP server (`backend/ttt/api/mcp_server.py`) exposes the chat agent
  to *other* MCP clients (e.g. Claude Code) via Streamable HTTP at `/mcp`.
  Two tools: `ttt_list_projects` and `ttt_ask`.
- Auto-accept everywhere is a deliberate stance — see PLAN.md §6.2. There
  is no propose-diff / human-in-the-loop review machinery and there
  shouldn't be.
- No RAG-style status pills, sentiment, or health scores. PLAN.md §6.8.
- The Webex token must never be logged. Comment to that effect lives in
  the `WebexConnector`.

## Out of scope for the wiki

- Step-by-step setup instructions (those live in the README).
- Connector implementation details for unfinished connectors (Confluence
  M6, Webex M7) — they're scaffolded but not real yet.
