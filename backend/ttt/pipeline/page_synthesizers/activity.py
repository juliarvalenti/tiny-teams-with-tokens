"""Activity page — filtered enumeration of recent commits / releases / issues.

Grounded by overview, glossary. Filters items to those that move or threaten
an active goal. Raw enumeration without filtering belongs in the source
deltas; this page is supposed to be the high-signal subset.
"""

from __future__ import annotations

from ttt.pipeline.page_synthesizers._common import (
    PageInputs,
    call_or_stub,
    deltas_block,
    grounded_context,
)

_GROUNDED_BY = ("overview.md", "glossary.md")

_SYSTEM_PROMPT = """You are writing the ACTIVITY page of a project's status wiki.

You will be given:
- The PROJECT NAME and CHARTER.
- The STABLE ANCHOR PAGES (overview, glossary). overview.md lists active goals. ONLY surface activity that relates to an active goal, or surfaces a risk to one. Filter ruthlessly.
- Three SOURCE DELTAS (GitHub / Confluence / Webex).

Produce a markdown page with these sections, in order:

## Releases
Bullets. Each bullet lists a release tag and a 1-line gloss explaining which goal it advanced. Skip releases that don't relate to a goal.

## Notable PRs / commits
Bullets. Each bullet is `<short-sha or PR#> — <one-line summary> — <which goal>`. If a commit doesn't relate to a goal, omit it. Maximum 8 bullets.

## Issues to watch
Bullets. Each bullet is `<#issue> [<labels>] — <title> — <why it matters>`. Include open bugs/security/oncall items, plus high-signal feature work. Maximum 8 bullets.

## Documentation changes
Bullets. Confluence pages updated where the change is non-trivial.

Rules:
- Every bullet ends with a citation in brackets, e.g. `[commit a1b2c3d]`, `[issue #142]`, `[release v1.0.6]`, `[page "Roadmap Q2"]`.
- Filter is the value-add of this page. Dumping everything is a failure mode. If you would have included more than 8 bullets in a section, pick the 8 most goal-relevant.
- If nothing in a section is goal-relevant, write `_(no goal-relevant activity this period)_` and move on. Do not omit headings.
- Do NOT include a Sources block at the end. Citations inline are sufficient.
- Output markdown only. No preamble. No frontmatter."""


async def write_activity(inputs: PageInputs) -> str:
    user = _build_user(inputs)
    fallback = _stub()
    return await call_or_stub(
        page_path="activity.md",
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
        "## Releases\n\n_(stub mode — no LLM filtering applied)_\n\n"
        "## Notable PRs / commits\n\n_(stub mode)_\n\n"
        "## Issues to watch\n\n_(stub mode)_\n\n"
        "## Documentation changes\n\n_(stub mode)_\n"
    )
