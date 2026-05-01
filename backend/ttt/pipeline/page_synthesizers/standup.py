"""Standup page — the 10-second TL;DR card surfaced above the wiki.

Three fixed H2 sections: "What is this", "Why care", "What's happening now".
The frontend renders each as an editable card; the agent sees plain markdown.

Tight token budget enforces brevity — if the prompt grows, this page should
not. It's the "scan, don't read" surface.
"""

from __future__ import annotations

from ttt.pipeline.page_synthesizers._common import (
    PageInputs,
    call_or_stub,
    deltas_block,
    grounded_context,
)

_GROUNDED_BY = ("overview.md", "team.md", "glossary.md")

_SYSTEM_PROMPT = """You are writing the STANDUP card for a project's status wiki.

This is the 10-second TL;DR a busy cross-functional stakeholder sees above the wiki. They will not scroll. They will not click in. Every word counts.

You will be given:
- The PROJECT NAME and CHARTER.
- The STABLE ANCHOR PAGES (overview/team/glossary).
- The PRIOR STANDUP (may be empty on first ingest).
- Three SOURCE DELTAS summarizing recent activity.

Produce a markdown page with EXACTLY these four sections, in order:

## What is this
One or two sentences. What the project is, in plain language. Treat the reader as someone who has never heard of it.

## Headline
One or two sentences. The single most important thing that happened this period — usually a ship, a slip, a major decision, or a new blocker. Lead with the noun, not the verb. If nothing notable happened, say so honestly.

## Asks / Blockers
Bullets. Where the team is stuck or needs help from someone outside the team. Look for: phrases like "blocked", "waiting on", "@<person>", unresolved issues with no movement, decisions awaiting input. Each bullet should be actionable — name what's needed and from whom if known. Cite supporting items in brackets, e.g. `[issue #142]`, `[#payments-eng 2026-04-26]`. If there are genuinely no asks, write `_(none — team is unblocked)_` and nothing else.

## Up next
Bullets. Forward-looking — upcoming milestones, dates, or in-flight work expected to land soon. Pull from open issues with milestones, deadlines mentioned in chat, "next sprint" mentions. Keep it short. If nothing is on the calendar, write `_(no scheduled milestones)_`.

Rules:
- Headings must be exactly as specified. No extras. No emojis. No status pills like "🟢 on track" — never invent a status indicator.
- Tight prose. No leadership-speak. No "in conclusion". No section preambles.
- Total length under ~200 words. If you need to cut, cut.
- Output markdown only. No frontmatter (the runner adds it). No code fences around the whole thing."""


async def write_standup(inputs: PageInputs) -> str:
    user = _build_user(inputs)
    fallback = _stub(inputs)
    return await call_or_stub(
        page_path="standup.md",
        system=_SYSTEM_PROMPT,
        user=user,
        fallback=fallback,
        max_tokens=600,
        temperature=0.2,
    )


def _build_user(inputs: PageInputs) -> str:
    parts = [f"PROJECT NAME: {inputs.project_name}"]
    if inputs.charter:
        parts.append(f"\nCHARTER:\n{inputs.charter}")
    parts.append(f"\nSTABLE ANCHOR PAGES:\n{grounded_context(inputs, _GROUNDED_BY)}")
    if inputs.prior_page_md.strip():
        parts.append(f"\nPRIOR STANDUP:\n{inputs.prior_page_md}")
    else:
        parts.append("\nPRIOR STANDUP: (none — this is the first ingest)")
    parts.append(f"\n{deltas_block(inputs)}")
    return "\n".join(parts)


def _stub(inputs: PageInputs) -> str:
    return (
        f"## What is this\n\n{inputs.project_name} — stub standup (no API key set).\n\n"
        "## Headline\n\n_(stub mode)_\n\n"
        "## Asks / Blockers\n\n_(none — team is unblocked)_\n\n"
        "## Up next\n\n_(no scheduled milestones)_\n"
    )
