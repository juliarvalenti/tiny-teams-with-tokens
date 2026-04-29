"""Shared helpers for the per-page synthesizer modules."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ttt.pipeline import anthropic_client
from ttt.reports import schema as report_schema

log = logging.getLogger("ttt.pipeline.page_synthesizers")


@dataclass
class PageInputs:
    project_name: str
    charter: str
    is_greenfield: bool
    github_delta: str
    confluence_delta: str
    webex_delta: str
    stable_pages: dict[str, str]  # path -> markdown body (frontmatter stripped)
    prior_page_md: str = ""       # the page's prior content, frontmatter stripped


def grounded_context(inputs: PageInputs, paths: tuple[str, ...]) -> str:
    parts: list[str] = []
    for p in paths:
        body = inputs.stable_pages.get(p, "").strip()
        if not body:
            continue
        title = report_schema.SPEC_BY_PATH[p].title if p in report_schema.SPEC_BY_PATH else p
        parts.append(f"### {title} ({p})\n\n{body}")
    return "\n\n".join(parts) if parts else "_(no anchor pages available)_"


def deltas_block(inputs: PageInputs) -> str:
    return (
        f"### GitHub delta\n{inputs.github_delta}\n\n"
        f"### Confluence delta\n{inputs.confluence_delta}\n\n"
        f"### Webex delta\n{inputs.webex_delta}"
    )


async def call_or_stub(
    *,
    page_path: str,
    system: str,
    user: str,
    fallback: str,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> str:
    """Run a synthesizer prompt, or fall back to `fallback` if no API key
    or the call fails. Caller passes a body without frontmatter; the runner
    is responsible for wrapping with frontmatter before persisting.
    """
    if not anthropic_client.is_available():
        log.info("ANTHROPIC_API_KEY missing — using stub for %s", page_path)
        return fallback

    from ttt.config import settings  # late import to avoid module-load deps

    try:
        text = await anthropic_client.complete(
            model=settings.synthesizer_model,
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:
        log.exception("synthesizer for %s failed; using fallback", page_path)
        return fallback + f"\n\n_(synthesis fell back to stub: {type(e).__name__})_"
    return text or fallback
