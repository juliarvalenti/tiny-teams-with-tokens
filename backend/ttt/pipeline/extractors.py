"""Per-source extraction.

Each connector returns pre-fetched markdown. The extractor's job is to
distill that into a tight delta the synthesizer can fold into the report —
no chit-chat, no reformatting of unrelated content. Tone is leadership-
facing: signal over completeness.

If ANTHROPIC_API_KEY is not set we fall back to a passthrough delta so the
local pipeline still produces something demoable.
"""

from __future__ import annotations

import logging

from ttt.config import settings
from ttt.pipeline import anthropic_client
from ttt.pipeline.chunking import maybe_chunk_and_summarize
from ttt.pipeline.connectors.base import FetchResult

log = logging.getLogger("ttt.pipeline.extractors")

_BASE_INSTRUCTIONS = """You are summarizing one source of activity for a status report consumed by engineering leadership and PMs.

Rules:
- Output markdown only. No preamble, no "Here is the summary".
- Lead with the highest-signal items first. Skip noise.
- Preserve concrete identifiers (commit SHAs, version tags, issue numbers, page titles, channel names) so they can be cited.
- Each bullet should end with a short bracketed citation referencing the source item, e.g. `[commit a1b2c3d]`, `[issue #142]`, `[page "Roadmap Q2"]`, `[chat #payments-eng 2026-04-26]`.
- Do not invent facts. If something is unclear in the source, omit it.
- Aim for 5-15 bullets total; group with `### Subheadings` when it helps readability.
- If the source has no meaningful new activity, output exactly: `_no notable activity_`."""

_PROMPTS: dict[str, str] = {
    "github": _BASE_INSTRUCTIONS + """

You are summarizing GitHub activity. Group as:
### Releases
### Commits / merged PRs
### Open issues worth surfacing (bugs, blockers, anything labeled oncall/security)""",
    "confluence": _BASE_INSTRUCTIONS + """

You are summarizing Confluence page changes. Group as:
### Recently updated pages
### New pages
Note who edited and a one-line description of what changed.""",
    "webex": _BASE_INSTRUCTIONS + """

You are summarizing Webex chat activity. Group as:
### Decisions / commitments made
### Open questions
### Notable discussions
Quote sparingly — paraphrase to capture the substance.""",
}


async def extract(fetch: FetchResult) -> str:
    """Return a markdown delta the synthesizer can consume."""
    if fetch.skipped:
        return f"_{fetch.source}: skipped ({fetch.skip_reason})_"
    if not fetch.markdown.strip():
        return f"_{fetch.source}: no new activity_"

    body = maybe_chunk_and_summarize(fetch.markdown)

    if not anthropic_client.is_available():
        log.info("ANTHROPIC_API_KEY missing — using passthrough delta for %s", fetch.source)
        return f"_(verbatim from {fetch.source}; no LLM extraction)_\n\n{body}"

    system = _PROMPTS.get(fetch.source, _BASE_INSTRUCTIONS)
    user = f"Source: {fetch.source}\n\n----- BEGIN SOURCE MARKDOWN -----\n{body}\n----- END SOURCE MARKDOWN -----"
    try:
        text = await anthropic_client.complete(
            model=settings.extractor_model,
            system=system,
            user=user,
            max_tokens=2048,
        )
    except Exception as e:
        log.exception("extractor for %s failed", fetch.source)
        return f"_{fetch.source}: extraction failed ({type(e).__name__})_"
    return text or f"_{fetch.source}: empty model response_"
