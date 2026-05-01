# tiny-teams-with-tokens — design plan & handoff

This is the load-bearing design doc. If you (human or agent) are picking this project up cold, read this end-to-end before changing anything. The README explains *what it does*; this doc explains *why it's built that way* and *what to do next*.

---

## 1. Problem

Cisco engineering teams are running small with heavy AI-agent leverage. Velocity is high, but cross-team and leadership-level visibility is poor: PRs land at machine speed, Webex chats blur, Confluence drifts. Status meetings are theater. We want a *DeepWiki-style live wiki per project* that leadership / PMs / cross-functional partners can scan in 30 seconds and trust.

Three integrations matter:

- **GitHub** — commits, releases, issues, PR review (real, implemented)
- **Confluence** — recently updated pages under configured roots (stub; needs Cisco creds)
- **Webex** — channel messages, meeting notes (stub; needs personal token + channel membership)

The product target audience is leadership, but engineers benefit too: cross-team dependency visibility without sync meetings.

---

## 2. The product realization that shaped the architecture

The first cut of TTT generated a single markdown report per ingest. The output looked like leadership prose but read as **vibes** — "rapid iteration signaling stability work" instead of substance. Diagnosis:

> A status report has no ground truth in its activity feed.
> **Signal is activity *measured against an explicit goal*.**

DeepWiki gets away without explicit goals because the code itself is ground truth (a function exists or it doesn't). For a status wiki, we don't have that. **We have to maintain the goals ourselves and measure activity against them.**

This insight forced two big decisions:

1. **Reports are wikis, not single documents.** A tree of pages with explicit roles.
2. **Pages are split into stable (the anchor) and dynamic (the measurement).** The anchor holds project identity + active goals; dynamic pages reference the anchor for grounding.

Without that split, every reingest re-derives identity from the latest activity → drift, vibes, no signal. With the split, identity is durable and dynamic pages have something to filter against.

---

## 3. Architecture

### 3.1 Data model

```
Project (sqlite)
├── id, name, charter, repos[], confluence_roots[], webex_channels[], locked, ...
├── reports[]: ingest-snapshot rows (version, ingested_at, summary, is_greenfield)
└── page_revisions[]: (path, markdown, author, message, created_at, report_id?)

Filesystem cache for the chat agent's Read/Edit/Write tools (regenerable):
data/wiki/<project_id>/
    ├── overview.md       (stable: purpose + active goals = "the anchor")
    ├── team.md           (stable)
    ├── glossary.md       (stable)
    ├── architecture.md   (stable)
    ├── status.md         (dynamic, grounded by overview/team/glossary)
    ├── activity.md       (dynamic, grounded by overview/glossary)
    └── conversations.md  (dynamic, grounded by overview/team)
```

Page kind is declared in YAML frontmatter. Hierarchy is path-derived (`a/b.md` is a child of `a.md`).

### 3.2 Page kinds

| Kind | Lifecycle | Edit semantics |
|---|---|---|
| **stable** | Written on **greenfield only**. Preserved across all subsequent reingests. | Human-curated. Edits durable forever. |
| **dynamic** | Rewritten on **every** ingest. Grounded by stable pages declared in `grounded_by` frontmatter. | Editable, but next ingest overwrites. UI surfaces a warning. |

There's no "agent proposes a diff, human reviews" loop. Auto-accept everywhere. Simplifies state machine, accepts that occasional resets are fine.

### 3.3 Pipeline

Greenfield ingest:

```
charter + 3 source deltas
  ↓ (founding synthesizer, single Haiku call → 4 stable pages)
  ↓
overview.md, team.md, glossary.md, architecture.md
  ↓
{ status, activity, conversations }
  ↓ (3 dynamic synthesizers in parallel, each grounded by its declared stable pages)
  ↓
status.md, activity.md, conversations.md
  ↓
all 7 pages → single git commit → Report row in sqlite
```

Incremental ingest:

```
prior pages loaded from git
stable pages preserved as-is
3 fresh deltas
  ↓
3 dynamic synthesizers (parallel), grounded by *current* stable pages + *prior* dynamic page content
  ↓
3 rewritten dynamic pages → single git commit → new Report row
```

Per call: extractors + dynamic synthesizers run in `asyncio.TaskGroup` for parallelism. Total LLM calls per ingest: ~7 (3 extractors + founding-or-skip + 3 dynamic). All Haiku currently — flip `synthesizer_model` to Opus in `config.py` for higher quality.

### 3.4 Connector layer

Each connector implements `async fetch(*, since: datetime | None) -> FetchResult` and returns pre-fetched markdown. Extractors then summarize per-source. Connectors are **independently failable** — a failed Webex fetch becomes `_(webex: skipped (...) )_` in the dynamic page deltas, doesn't break the run.

Real connectors:

- `pipeline/connectors/github.py` — httpx, GitHub REST API. Fetches releases, commits, issues + PRs since `last_ingested_at`. Routes issues with high-signal labels (bug/oncall/security/blocker/incident/p0/p1) into a separate section. Auth optional (uses `GITHUB_TOKEN` if set; otherwise unauthenticated 60/hr/IP).

Stub connectors (return fixture content, signal "not implemented"):

- `pipeline/connectors/confluence.py` — needs `CONFLUENCE_BASE_URL/USER/TOKEN`. Plan: `atlassian-python-api`, traverse pages under each configured root, fetch recent updates.
- `pipeline/connectors/webex.py` — needs personal access token (~12h lifetime). Plan: `httpx` calls, list configured channels, paginate messages since last ingest.

### 3.5 Frontend

- **Next.js 15.5.15 + Tailwind + SWR**. App Router. Fully client-rendered detail page (SWR with `refreshInterval` that adapts based on the project's `locked` flag).
- **Milkdown Crepe 7.20.0** as the WYSIWYG markdown editor. Markdown is the *model* (remark AST), so edits round-trip clean. Mounted via a thin `forwardRef` wrapper in `components/CrepeEditor.tsx`.
- Wiki sidebar (`components/WikiSidebar.tsx`) builds a tree from page paths, renders kind badges with tooltips explaining the lifecycle, supports "+ new page" at any level.

### 3.6 Backend

- **FastAPI + SQLModel + uvicorn**. SQLite for ergonomics; swap to Postgres if/when this leaves PoC.
- Background tasks via `asyncio.create_task` from async handlers. The handler creates an `IngestRun` row, dispatches the runner, returns immediately. No Celery/RQ.
- All async — handlers, runner, connectors, anthropic client.

### 3.7 LLM access

`pipeline/anthropic_client.py` is a thin wrapper:

- Lazy `AsyncAnthropic` singleton (so import doesn't require a key)
- Retry with exponential backoff on `RateLimitError` and 5xx `APIStatusError`
- `is_available()` check used by every synthesizer/extractor to gate real calls — if `ANTHROPIC_API_KEY` is empty, falls back to deterministic stubs so dev / tests still produce structurally-valid output

### 3.8 Why no agent SDK?

We researched. The "Anthropic Agent SDK" doesn't exist as a separate framework — it's the regular `anthropic` Python SDK + Messages API + tool use. There's no first-class subagent primitive; the canonical pattern for fan-out is exactly what we built (`asyncio.TaskGroup` over parallel `messages.create()` calls). Adding a heavier abstraction would only obscure things.

---

## 4. Audit & versioning

Every ingest produces a `Report` row + N `PageRevision` rows (one per page) sharing that `report_id`. Every human or chat edit produces one `PageRevision` row with `report_id=NULL`. The audit trail is a query — no git substrate, no pointer-update bug class.

```sql
SELECT created_at, author, message FROM pagerevision
 WHERE project_id = ? AND path = 'overview.md'
 ORDER BY created_at DESC;
```

Roll back to a prior revision: insert a new `PageRevision` whose markdown is taken from the historical row. The `data/wiki/<project_id>/` filesystem mirror is regenerable via `report_repo.sync_to_disk(project_id)`.

---

## 5. Project state by milestone

| Milestone | Status |
|---|---|
| M1: backend + frontend scaffolding, DB, git report repo | ✅ done |
| M2: mock pipeline producing structured reports | ✅ done (then superseded by wiki refactor) |
| M3: end-to-end UI with Crepe editor | ✅ done |
| M4: real Anthropic agent calls (Haiku) with retry/backoff | ✅ done |
| M5: real GitHub connector | ✅ done |
| **Wiki refactor: pages, anchor + dynamic split, founding synthesizer** | ✅ **done — current state of `main`** |
| M6: real Confluence connector | ⏸ blocked on creds |
| M7: real Webex connector | ⏸ blocked on creds + channel access |
| M8: standalone MCP server exposing the wiki to other Claude Code sessions | ⏳ next |

Tests: 6 currently (4 schema + 2 pipeline). All run in stub mode (no API key) — `pytest -x -q` from the repo root. CI is not set up; would be a one-file GitHub Actions addition.

---

## 6. Decisions worth knowing about

These are decisions that look small but reshaped the project. Don't undo them without reading the rationale.

### 6.1 Wiki shape (vs. single-doc)

**Decision:** every project's report is a directory of markdown pages, not one file.

**Why:** The original `pages: []` data model was right; collapsing to single-doc was a PoC simplification that bit us. Single-doc forced the synthesizer to re-derive project identity from each ingest's activity, which produces vibes-coded prose. The wiki shape lets us pin identity (stable pages) and measure against it (dynamic pages).

### 6.2 Stable / dynamic with auto-accept (vs. propose-diff)

**Decision:** stable pages are written on greenfield only; preserved across reingests. Dynamic pages are rewritten every ingest. No human-in-the-loop review step.

**Why:** Propose-diff machinery (agent proposes a stable-page change, human accepts/rejects in UI) is real complexity for marginal value at PoC scale. Auto-accept everywhere keeps the state machine simple. If a stable page drifts and needs refresh, the user can edit by hand, or delete-and-reingest to trigger the founding pass again. Future work can revisit this if it becomes a real pain.

### 6.3 Goal-grounded synthesis (vs. activity-driven)

**Decision:** dynamic-page system prompts inject the relevant stable pages (`grounded_by` frontmatter) so the model has goals/glossary/team in context every call.

**Why:** This is the mechanism that turns activity into signal. `activity.md`'s prompt explicitly says "if a commit doesn't relate to a goal, omit it." `status.md` has a "Goal progress" section that walks the goals from `overview.md`. Without grounding, you get vibes; with grounding, filtering is mechanical.

### 6.4 Git as the audit substrate (vs. a `report_edits` table)

**Decision:** report content lives in a git repo; sqlite holds pointers. Every change — agent or human — is a commit.

**Why:** Free versioning, free diff, free blame, free rollback. No bespoke schema. Editor-native (engineers can `git clone` and grep). The cost — shelling out to `git` instead of using a Python library — is small and avoids a heavy dep.

### 6.5 Milkdown Crepe (vs. Tiptap / Lexical / BlockNote)

**Decision:** Milkdown Crepe for WYSIWYG, because markdown is its **internal model** (remark AST), not an export format. Round-trip is the design center.

**Why:** Editors that use a JSON document model and treat markdown as a serializer (Tiptap, BlockNote, Plate, Lexical-with-markdown-plugin) lose fidelity on tables, footnotes, custom marks. We need exact round-trip because markdown is the source of truth in git. Crepe pulls some heavy transitive deps (codemirror, katex, vue) for ~250kB gzipped — accepted trade for correctness.

Bus factor: Saul-Mirone is the sole npm publisher. Pinning + lockfile + `npm ci` blocks future supply-chain poison; that's our hedge.

### 6.6 Haiku for everything (vs. Opus for synthesis)

**Decision:** PoC uses `claude-haiku-4-5` for every call (extractors + synthesizers).

**Why:** Cheap. A full ingest is ~7 calls = pennies. Quality is good enough for a PoC, especially with goal-grounding doing heavy lifting. To upgrade synthesis quality, change `synthesizer_model` in `config.py` to `claude-opus-4-7` — extractors stay Haiku.

### 6.7 No DAG framework

**Decision:** plain `asyncio.TaskGroup` for parallelism. No Airflow/Prefect/Dagster/Celery.

**Why:** The pipeline is 4-7 nodes with one fan-out. A workflow engine adds infra cost (database, scheduler, web UI, worker pool) for zero benefit at this scale. If we ever need scheduled ingest, retries-with-backoff, or fan-out across many projects, we revisit.

### 6.8 Connectors are independently failable

**Decision:** if a connector fails, we surface `_(source: skipped (reason) )_` in the deltas and continue. Never abort the whole ingest.

**Why:** Connectors fail for predictable reasons — token expired (Webex), not a member of a channel, repo permissions, rate limit. Halting on any of these kills the report; degraded reports are still useful.

---

## 7. Where to find things

```
backend/ttt/
├── api/
│   ├── projects.py          CRUD + reingest dispatch
│   └── reports.py           page tree GET, per-page GET/PUT, page CREATE
├── reports/
│   ├── repo.py              all git operations (write_pages, read_page, list_pages)
│   └── schema.py            DEFAULT_PAGES, frontmatter helpers, build_tree, validate_pages
├── pipeline/
│   ├── runner.py            ⭐ orchestrator — start here when reading
│   ├── extractors.py        per-source distillation prompts (Haiku)
│   ├── chunking.py          stub for hierarchical summarize on large windows (M-future)
│   ├── anthropic_client.py  retry-wrapped messages.create
│   ├── connectors/
│   │   ├── base.py          Connector protocol + FetchResult
│   │   ├── github.py        ⭐ real connector — copy this shape for confluence/webex
│   │   ├── confluence.py    stub
│   │   ├── webex.py         stub
│   │   └── mock.py          reads backend/ttt/fixtures/*.md
│   └── page_synthesizers/
│       ├── _common.py       PageInputs, grounded_context, deltas_block, call_or_stub
│       ├── founding.py      ⭐ writes the 4 stable pages on greenfield
│       ├── status.py        dynamic
│       ├── activity.py      dynamic
│       └── conversations.py dynamic
├── models.py                Project, Report, IngestRun
├── main.py                  FastAPI app + lifespan (init_db, init_report_repo)
├── config.py                pydantic-settings, model picks
├── db.py                    SQLModel engine
└── cli.py                   `ttt init-data`

frontend/
├── app/
│   ├── page.tsx             projects list (SWR)
│   ├── projects/new/page.tsx new-project form
│   └── projects/[id]/page.tsx ⭐ wiki UI (sidebar + editor)
├── components/
│   ├── WikiSidebar.tsx      tree, kind badges, +new-page button
│   ├── ReportEditor.tsx     per-page edit/save, stable/dynamic warning
│   ├── CrepeEditor.tsx      thin Milkdown wrapper, forwardRef getMarkdown()
│   └── ReingestButton.tsx
└── lib/api.ts               typed client for the FastAPI endpoints

data/                        gitignored; sqlite + bare git repo at runtime
.env.example → .env          ANTHROPIC_API_KEY (and optional connector tokens)
docker-compose.yml           backend + frontend + named volume for /data
backend/Dockerfile           python:3.12-slim + uv + git
frontend/Dockerfile          node:20-alpine + next dev (PoC simplicity)
pyproject.toml + uv.lock     Python deps (sync via `uv sync --group dev`)
frontend/package.json + lock npm deps (install via `npm ci`)
```

---

## 8. Where to go next (in priority order)

### 8.0 In-app chat with project-scoped tool use (top-of-mind next step)

A side panel on the project detail page where leadership can ask deep-dive questions: *"why did v1.0.7rc1 slip the original date?"*, *"what's the latest on issue #175?"*, *"who owns the SSE leak fix?"* The chat should have read-only access to:

1. **The current wiki** — list pages, read a page (the cheapest, most-trusted context).
2. **Live GitHub** — search/fetch issues, PRs, commits, releases beyond what the wiki has captured. Useful for "tell me about #142" follow-ups.
3. **Live Confluence** — search pages, fetch page bodies. Useful for "summarize the design doc on X."
4. **Live Webex** — search messages in configured channels. Useful for "what did the team discuss about Y?"

**Architecture sketch:**

- Anthropic Messages API with tool use loop. The model calls a tool → server executes → result returned → model continues until `stop_reason: "end_turn"`.
- System prompt seeded with the project's `overview.md` + `team.md` + `glossary.md` so the model has anchor context before any tools are called. Cheap context, big quality win.
- Tools scoped to the *current project's* sources (the project's `repos`, `confluence_roots`, `webex_channels`). No cross-project leakage.
- Streaming responses (`client.messages.stream`) for snappy UX.
- Conversations persist per-project in sqlite (new `Conversation` and `Message` tables). One open conversation per project at a time is fine for v1; multi-thread later.
- Model: Sonnet for chat (better tool-use reasoning than Haiku, cheaper than Opus). Configurable in `config.py`.

**Tool surface (proposed):**

```
read_page(path)                       — current wiki
list_pages()                          — wiki index
github_get_issue(repo, number)
github_get_pr(repo, number)
github_search(repo, query)            — GH search API
github_list_commits(repo, since, ...)
confluence_search(query)              — narrowed to project's roots
confluence_get_page(page_id)
webex_search_messages(query, channel) — narrowed to project's channels
```

All tools are read-only. **Do not add wiki-edit tools in v1** — the chat agent reading and the human editing should stay separate concerns until we're confident on the chat's reliability.

**UX**: side panel on `/projects/[id]/`, collapsible. Each turn renders streaming markdown. Tool calls render as collapsible "🔍 looked up issue #175" affordances so users can see what was consulted (and click through).

**Cost**: tool-use loops can be expensive on large repos. Mitigations: (a) inject the wiki summary up-front so most questions are answerable from cached context, (b) cap tool-call iterations per turn (5-10), (c) use Sonnet not Opus.

**Why this is a high-leverage next step**: the wiki is one-way today. Leadership reads it. Chat makes the wiki *queryable*, which is what most of them will actually want — the static report answers "what's happening?" and the chat answers "tell me more about X." Together they replace a lot of status meetings.

### 8.1 Real Confluence connector (M6)

Mirror `pipeline/connectors/github.py`'s shape. `atlassian-python-api` is already in optional deps. Auth via `CONFLUENCE_BASE_URL` + `CONFLUENCE_USER` + `CONFLUENCE_TOKEN`.

What to fetch:

- For each page in `project.confluence_roots`, walk descendants
- Filter to pages updated since `since`
- Title, last-editor, short body excerpt, link

Format the markdown output to mirror `backend/ttt/fixtures/confluence.md`. Update `pipeline/runner.connectors_for(project)` to wire the real connector when `confluence_roots` and creds are both present.

### 8.2 Real Webex connector (M7)

Same shape, but auth lifecycle is the gnarly part. Personal access tokens last ~12h, so:

- Reingest is human-triggered for now, not scheduled
- Surface a clear "token expired — paste a new one" UX
- Channel membership: list channels we *can't* see and surface as warnings rather than silently producing thin reports
- **Never log the token.** Already noted in the connector stub. Add a redaction filter on the IngestRun.log writer if we ever start writing tokens to logs.

### 8.3 MCP server (M8)

A separate Python process (`backend/ttt/mcp_server.py`) using the MCP Python SDK that exposes:

- `list_projects()` — name, latest version, lock state
- `get_latest_report(project_name)` — page tree
- `get_report_section(project_name, page_path)` — markdown of a single page
- (stretch) `search(query)` — full-text across all wikis

This makes the wiki readable by *other* Claude Code sessions across the org. That's a much bigger value prop than the dashboard alone, and it's nearly free once the wiki exists.

### 8.4 Citation links

Citations are markdown text right now (`[commit a1b2c3d]`). Add a renderer-side post-process that resolves common forms to URLs:

- `[commit <sha>]` → link to the configured GitHub repo
- `[issue #N]` → same
- `[release vX.Y]` → same
- `[page "Title"]` → link to Confluence page
- `[chat #channel YYYY-MM-DD]` → link to Webex channel

Either a remark plugin (cleanest) or a string replacement at the API layer. Project config holds the canonical repo / Confluence base URL / Webex workspace.

### 8.5 Hierarchical wiki (already partially supported)

Path-derived hierarchy works (`architecture/design.md` is a child of `architecture.md`). The "+ new page" button creates pages under any parent. Worth doing:

- Drag-to-reorder in the sidebar
- Rename / move pages (currently can't, would need to update file paths *and* any markdown links to them)
- Delete pages (currently can't either)

### 8.6 Multi-project queries

Once you have multiple projects, leadership wants cross-cuts: "show me everything labeled `oncall` across all projects this week," "which projects have unresolved blockers older than 30 days?" The data is all there in git + sqlite. A simple query API + UI page would deliver real value.

### 8.7 Anchor regeneration

Currently the only way to refresh stable pages is to delete-and-reingest. A "regenerate anchor" button on the project detail page that re-runs the founding synthesizer (preserving human edits the user wants kept) would be useful. Easy to add a `?force_anchor=true` flag on the reingest endpoint.

### 8.8 Testing strategy

Tests are stub-mode only. Worth adding:

- A few real-API integration tests gated on `ANTHROPIC_API_KEY` being set, run manually before releases
- API endpoint tests via FastAPI TestClient
- Frontend tests are entirely absent — Playwright on the create-project / edit-page / reingest flow would catch regressions

### 8.9 Production hardening

This is a PoC. Do not deploy as-is. Things to do before:

- Auth on the API (currently anyone with network access can do anything)
- Postgres instead of SQLite
- Frontend builds in production mode (Dockerfile currently uses `next dev` for PoC simplicity)
- Centralized logging with token redaction
- Rate-limit-per-user on the reingest endpoint
- Don't trust `project.charter` in prompts without sanitization (potential prompt injection if charters become user-supplied across orgs)

---

## 9. Open product questions

- **What's a project?** Right now a project is "one or more GitHub repos + a charter + some Confluence/Webex sources." Should a project be more aligned with a team, a product, or a deliverable? This affects how `overview.md`'s goals get framed.
- **Goal lifecycle.** Active goals in `overview.md` are written once at greenfield. They should evolve — quarterly OKRs, shipped milestones get archived. We don't have a "complete a goal" or "shift a goal" UX. Probably needed before this scales.
- **Multi-tenant isolation.** Single sqlite, single git repo, single anthropic key. Fine for a team-of-one PoC; falls apart for an org-wide rollout.
- **The "context graph" question.** The team's original instinct was to build a structured context graph instead of free-form pages. We pushed back and chose pages-as-LLM-context because (a) it's faster to build, (b) the LLM is already good at consuming markdown, (c) we can always extract structure later if we need it. Worth revisiting if we hit cases where free-form prose is genuinely insufficient — e.g., "give me every commitment with a deadline" needs structured data, not prose to scan.

---

## 10. How to pick this up cold (for an agent)

1. Read this file end-to-end. Don't skim section 6.
2. Read `backend/ttt/pipeline/runner.py`. It's the spine.
3. Read `backend/ttt/reports/schema.py`. It defines the page model.
4. Read `backend/ttt/pipeline/page_synthesizers/founding.py`. It defines what the anchor *is*.
5. Skim one dynamic synthesizer — `status.py` is probably the most informative.
6. Run `docker compose up --build` (need `ANTHROPIC_API_KEY` in `.env`). Create a project pointing at any public GitHub repo. Watch the wiki appear.
7. Look at `overview.md` in the UI, then `status.md`. Compare to what you'd expect if the project were a single document — that delta is the architectural pay-off.
8. Pick a milestone from section 8 and go.

If you find yourself wanting to break a section-6 decision, write down *why* before doing it. Most of those decisions emerged from a wrong first attempt; reverting them without thinking will recreate the wrong attempt.
