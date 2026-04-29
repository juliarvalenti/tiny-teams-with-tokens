"""GitHub connector — real fetch via httpx + GitHub REST API.

Pulls recent commits, releases, open issues (with high-signal labels), and
recently merged PRs across one or more `org/repo` slugs. Auth is optional —
unauthenticated requests get 60/hr per IP, which is fine for occasional
dev ingest of a couple repos. Provide GITHUB_TOKEN for higher limits.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ttt.pipeline.connectors.base import FetchResult

log = logging.getLogger("ttt.connectors.github")

API = "https://api.github.com"
GREENFIELD_WINDOW = timedelta(days=14)
HIGH_SIGNAL_LABELS = {"bug", "oncall", "security", "blocker", "incident", "p0", "p1"}
MAX_PER_KIND = 25


def _parse_repo(slug: str) -> tuple[str, str]:
    s = slug.strip().rstrip("/")
    if s.startswith("https://github.com/"):
        s = s[len("https://github.com/") :]
    elif s.startswith("github.com/"):
        s = s[len("github.com/") :]
    if s.endswith(".git"):
        s = s[: -len(".git")]
    parts = s.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"can't parse repo slug: {slug!r}")
    return parts[0], parts[1]


class GithubConnector:
    name = "github"

    def __init__(self, repos: list[str], token: str = "") -> None:
        self._repos = repos
        self._token = token

    def _headers(self) -> dict[str, str]:
        h = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "tiny-teams-with-tokens",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def fetch(self, *, since: datetime | None = None, **_: object) -> FetchResult:
        if not self._repos:
            return FetchResult(
                source=self.name,
                markdown="",
                skipped=True,
                skip_reason="no repos configured",
            )

        window_start = since or (datetime.now(timezone.utc) - GREENFIELD_WINDOW)
        # GitHub wants RFC3339 / ISO 8601 with Z
        since_iso = window_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        sections: list[str] = []
        sections.append(f"# GitHub activity (since {since_iso})")
        any_data = False

        async with httpx.AsyncClient(timeout=20.0, headers=self._headers()) as client:
            for slug in self._repos:
                try:
                    owner, repo = _parse_repo(slug)
                except ValueError as e:
                    sections.append(f"\n## {slug}\n\n_(skipped: {e})_")
                    continue
                try:
                    repo_md = await _fetch_one_repo(client, owner, repo, since_iso, window_start)
                    sections.append(repo_md)
                    any_data = True
                except httpx.HTTPStatusError as e:
                    msg = f"HTTP {e.response.status_code} on {owner}/{repo}"
                    if e.response.status_code in (401, 403):
                        msg += " (auth or rate limit)"
                    log.warning(msg)
                    sections.append(f"\n## {owner}/{repo}\n\n_(fetch failed: {msg})_")
                except Exception as e:
                    log.exception("github fetch failed for %s/%s", owner, repo)
                    sections.append(f"\n## {owner}/{repo}\n\n_(fetch failed: {type(e).__name__}: {e})_")

        if not any_data:
            return FetchResult(
                source=self.name,
                markdown="\n".join(sections),
                skipped=True,
                skip_reason="all configured repos failed",
            )
        return FetchResult(source=self.name, markdown="\n".join(sections))


async def _fetch_one_repo(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    since_iso: str,
    window_start: datetime,
) -> str:
    base = f"{API}/repos/{owner}/{repo}"
    out: list[str] = [f"\n## {owner}/{repo}"]

    # Releases — list and filter by created_at >= window_start
    rels = await _get_json(client, f"{base}/releases", params={"per_page": MAX_PER_KIND})
    rels_recent = [
        r for r in rels
        if r.get("created_at") and _parse_iso(r["created_at"]) >= window_start
    ]
    if rels_recent:
        out.append("\n### Releases")
        for r in rels_recent[:MAX_PER_KIND]:
            tag = r.get("tag_name") or r.get("name") or "(unnamed)"
            created = (r.get("created_at") or "")[:10]
            body = (r.get("body") or "").strip().splitlines()
            first = body[0] if body else ""
            out.append(f"- **{tag}** ({created}): {first[:240]}")

    # Commits since window_start
    commits = await _get_json(
        client, f"{base}/commits", params={"since": since_iso, "per_page": MAX_PER_KIND}
    )
    if commits:
        out.append("\n### Commits")
        for c in commits[:MAX_PER_KIND]:
            sha = c.get("sha", "")[:7]
            commit = c.get("commit") or {}
            author = (commit.get("author") or {}).get("name", "?")
            date = ((commit.get("author") or {}).get("date") or "")[:10]
            msg = (commit.get("message") or "").splitlines()[0]
            out.append(f"- `{sha}` ({date}, {author}): {msg[:200]}")

    # Issues + PRs since window_start. /issues returns both; PRs have a `pull_request` key.
    issues_and_prs = await _get_json(
        client,
        f"{base}/issues",
        params={"since": since_iso, "state": "all", "per_page": MAX_PER_KIND * 2},
    )
    issues_high_signal: list[dict[str, Any]] = []
    issues_other: list[dict[str, Any]] = []
    prs_recent: list[dict[str, Any]] = []
    for item in issues_and_prs:
        if item.get("pull_request"):
            prs_recent.append(item)
        else:
            labels = {(lb.get("name") or "").lower() for lb in (item.get("labels") or [])}
            if labels & HIGH_SIGNAL_LABELS:
                issues_high_signal.append(item)
            else:
                issues_other.append(item)

    if issues_high_signal:
        out.append("\n### High-signal issues")
        for it in issues_high_signal[:MAX_PER_KIND]:
            out.append(_fmt_issue(it))
    if issues_other:
        out.append("\n### Other recent issues")
        for it in issues_other[:MAX_PER_KIND]:
            out.append(_fmt_issue(it))
    if prs_recent:
        out.append("\n### Recent PRs")
        for it in prs_recent[:MAX_PER_KIND]:
            n = it.get("number")
            title = it.get("title", "").strip()
            state = it.get("state", "")
            user = (it.get("user") or {}).get("login", "?")
            updated = (it.get("updated_at") or "")[:10]
            merged_marker = " (merged)" if it.get("pull_request", {}).get("merged_at") else ""
            out.append(f"- #{n} [{state}{merged_marker}] \"{title}\" — {user}, updated {updated}")

    if len(out) == 1:
        out.append("\n_(no activity in window)_")
    return "\n".join(out)


def _fmt_issue(it: dict[str, Any]) -> str:
    n = it.get("number")
    title = it.get("title", "").strip()
    state = it.get("state", "")
    labels = ", ".join(lb.get("name", "") for lb in (it.get("labels") or []) if lb.get("name"))
    user = (it.get("user") or {}).get("login", "?")
    updated = (it.get("updated_at") or "")[:10]
    label_str = f" [{labels}]" if labels else ""
    return f"- #{n}{label_str} [{state}] \"{title}\" — {user}, updated {updated}"


async def _get_json(client: httpx.AsyncClient, url: str, *, params: dict[str, Any] | None = None) -> Any:
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def _parse_iso(s: str) -> datetime:
    # GitHub gives `2026-04-22T12:00:00Z`
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)
