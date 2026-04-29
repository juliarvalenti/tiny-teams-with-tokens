"""Conversations page — decisions / open questions / escalations from chat.

Grounded by overview, team. Captures the human side: what people committed
to, what they're stuck on, what they're escalating. Discrete from
status.md (which is interpretation) and activity.md (which is artifacts).
"""

from __future__ import annotations

from ttt.pipeline.page_synthesizers._common import (
    PageInputs,
    call_or_stub,
    deltas_block,
    grounded_context,
)

_GROUNDED_BY = ("overview.md", "team.md")

_SYSTEM_PROMPT = """You are writing the CONVERSATIONS page of a project's status wiki.

You will be given:
- The PROJECT NAME and CHARTER.
- The STABLE ANCHOR PAGES (overview, team).
- Three SOURCE DELTAS — note that the WEBEX delta is the primary source for this page; GitHub PR review comments and Confluence page comments are secondary.

Produce a markdown page with these sections, in order:

## Decisions and commitments
Bullets capturing what people committed to in conversations. Format: `**<who>**: <what they committed to> — <by when, if specified>`. End each with a citation, e.g. `[chat #payments-eng 2026-04-26]`.

## Open questions
Bullets. Each is a genuine unresolved decision — not rhetorical. Format: `<the question> — raised by <who>`. End with a citation.

## Escalations and concerns
Bullets. Anything explicitly flagged as a blocker, risk, or pulled into a leadership channel. End with a citation.

Rules:
- Filter to substance. Banter, status check-ins, "thanks!" replies are noise.
- Attribute by name when the source data has names. Anonymize if it doesn't.
- Each bullet should be self-contained: a leader scanning should understand without context.
- If a section has nothing, write `_(none surfaced this period)_` and move on. Do not omit headings.
- Output markdown only. No preamble. No frontmatter."""


async def write_conversations(inputs: PageInputs) -> str:
    user = _build_user(inputs)
    fallback = _stub()
    return await call_or_stub(
        page_path="conversations.md",
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
    parts.append(f"\n{deltas_block(inputs)}")
    return "\n".join(parts)


def _stub() -> str:
    return (
        "## Decisions and commitments\n\n_(stub mode)_\n\n"
        "## Open questions\n\n_(stub mode)_\n\n"
        "## Escalations and concerns\n\n_(stub mode)_\n"
    )
