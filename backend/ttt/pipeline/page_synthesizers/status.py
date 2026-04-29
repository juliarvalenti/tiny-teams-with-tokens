"""Status page — leadership-facing snapshot at this point in time.

Grounded by overview, team, glossary. Goal-oriented: every claim should
relate to an active goal from overview.md.
"""

from __future__ import annotations

from ttt.pipeline.page_synthesizers._common import (
    PageInputs,
    call_or_stub,
    deltas_block,
    grounded_context,
)

_GROUNDED_BY = ("overview.md", "team.md", "glossary.md")

_SYSTEM_PROMPT = """You are writing the STATUS page of a project's status wiki.

You will be given:
- The PROJECT NAME and CHARTER.
- The STABLE ANCHOR PAGES (overview/team/glossary). The OVERVIEW lists the project's active goals. Treat those goals as the lens through which all activity should be filtered.
- The PRIOR STATUS PAGE (may be empty on first ingest).
- Three SOURCE DELTAS summarizing recent activity.

Produce a markdown page with these sections, in order:

## Goal progress
For each active goal listed in overview.md, write 1-3 lines describing how this period's activity moved (or didn't move) that goal. If activity didn't touch a goal, say so explicitly — silence is information. Cite supporting items in brackets, e.g. `[commit a1b2c3d]`, `[issue #142]`, `[chat #payments-eng 2026-04-26]`.

## Headline this period
A 2-3 sentence executive summary. Lead with the single most important thing that happened. If nothing notable happened, say that.

## Decisions made
Bullets. Decisions that were committed to (in chat, in PR review, in design docs). Each bullet ends with a citation.

## Things that surprised us
Bullets. Anything that ran counter to expectations or the prior status. Each bullet ends with a citation.

Rules:
- Do NOT redescribe what the project IS. That's overview.md's job. Reference it; don't restate it.
- Do NOT list raw activity. activity.md handles that. Status is interpretation, not enumeration.
- If a section has no content, write `_(none this period)_` and move on. Do not omit the heading.
- Output markdown only. No preamble. No frontmatter (the runner adds that)."""


async def write_status(inputs: PageInputs) -> str:
    user = _build_user(inputs)
    fallback = _stub(inputs)
    return await call_or_stub(
        page_path="status.md",
        system=_SYSTEM_PROMPT,
        user=user,
        fallback=fallback,
        max_tokens=2048,
        temperature=0.3,
    )


def _build_user(inputs: PageInputs) -> str:
    parts = [f"PROJECT NAME: {inputs.project_name}"]
    if inputs.charter:
        parts.append(f"\nCHARTER:\n{inputs.charter}")
    parts.append(f"\nSTABLE ANCHOR PAGES:\n{grounded_context(inputs, _GROUNDED_BY)}")
    if inputs.prior_page_md.strip():
        parts.append(f"\nPRIOR STATUS PAGE:\n{inputs.prior_page_md}")
    else:
        parts.append("\nPRIOR STATUS PAGE: (none — this is the first ingest)")
    parts.append(f"\n{deltas_block(inputs)}")
    return "\n".join(parts)


def _stub(inputs: PageInputs) -> str:
    if inputs.is_greenfield:
        head = "Greenfield ingest — initial founding snapshot."
    else:
        head = "Continuing from prior report."
    return (
        "## Goal progress\n\n_(none this period — stub mode without API key)_\n\n"
        f"## Headline this period\n\n{head}\n\n"
        "## Decisions made\n\n_(none this period)_\n\n"
        "## Things that surprised us\n\n_(none this period)_\n"
    )
