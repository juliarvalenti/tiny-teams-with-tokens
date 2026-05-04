"""Per-repo ingest steering via `.ttt/wiki.md`.

llms.txt-style: a repo can drop a `.ttt/wiki.md` at its root with free-form
markdown context for the ingest agent — what the project is, what to
emphasize, which files in the repo are the canonical sources of truth, etc.
The agent receives the file body verbatim in its system prompt and follows
any links inside via the github MCP file tools.

Missing file = no-op. No schema, no parser — markdown in, markdown out.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger("ttt.pipeline.wiki_steering")

STEERING_PATH = ".ttt/wiki.md"
API = "https://api.github.com"


def _normalize_repo(repo: str) -> str | None:
    s = repo.strip().rstrip("/")
    for prefix in ("https://github.com/", "github.com/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    if s.endswith(".git"):
        s = s[: -len(".git")]
    parts = s.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}/{parts[1]}"


async def fetch_steering(repos: list[str], token: str = "") -> list[tuple[str, str]]:
    """Fetch `.ttt/wiki.md` from each repo. Returns `[(repo, body), ...]` for
    every repo that had one. Network failures and 404s are silent."""
    out: list[tuple[str, str]] = []
    if not repos:
        return out

    headers = {
        "Accept": "application/vnd.github.raw",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ttt-ingest-agent",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        for raw_repo in repos:
            repo = _normalize_repo(raw_repo)
            if not repo:
                continue
            try:
                resp = await client.get(
                    f"{API}/repos/{repo}/contents/{STEERING_PATH}"
                )
            except httpx.HTTPError as e:
                log.debug("steering fetch failed for %s: %s", repo, e)
                continue
            if resp.status_code == 404:
                continue
            if resp.status_code != 200:
                log.debug("steering %s returned HTTP %s", repo, resp.status_code)
                continue
            body = resp.text.strip()
            if body:
                out.append((repo, body))

    return out
