"""Founding-snapshot synthesizer.

Runs once per project on greenfield ingest. Reads everything we know about
the project (charter + 3 source deltas) and produces the four stable
pages: overview, team, glossary, architecture. These become the durable
anchor that future ingests reference but do not rewrite.

Output format: a single response containing four named sections; we split
locally into the four page bodies. One LLM call instead of four cuts cost
~4x and lets the model maintain consistency across pages.
"""

from __future__ import annotations

import re

from ttt.pipeline.page_synthesizers._common import (
    PageInputs,
    call_or_stub,
    deltas_block,
)
from ttt.reports import schema as report_schema

_SECTION_RE = re.compile(r"^===PAGE:\s*([a-z]+\.md)\s*===\s*$", re.MULTILINE)

_SYSTEM_PROMPT = """You are establishing the FOUNDING SNAPSHOT for a software project's status wiki.

You will be given the project name, an initial charter from the project lead, and three source deltas (GitHub / Confluence / Webex).

Produce exactly FOUR pages, each separated by a delimiter line of the form `===PAGE: <filename> ===`. The four pages, in order, are:

===PAGE: overview.md===
A concise project anchor. Sections in this order:
  ## Purpose       (2-3 sentences: what this project is and who it's for. NOT a changelog. NOT a feature list. The reason it exists.)
  ## Active goals  (3-6 bullets, concrete and measurable where possible. These are the goals that future status reports will measure activity against.)
  ## Out of scope  (optional: 0-3 bullets clarifying what this project is NOT)

===PAGE: team.md===
  ## Contributors  (people you can identify from commits / chat / page edits, with one-line role hint)
  ## Stakeholders  (anyone explicitly mentioned as a decision-maker or recipient of the work)
  ## Working rhythms (any rituals visible in the data: standups, releases, oncall rotations — only if visible. omit if unclear)

===PAGE: glossary.md===
  A bullet list. Each bullet is `**term**: definition`. Include acronyms, project-specific names, and any jargon that appeared in the source data and would confuse a new reader. Order alphabetically.

===PAGE: architecture.md===
  ## Shape       (2-4 sentences: high-level system shape — what runs where, what talks to what)
  ## Components  (bullets: name → 1-line description, only components actually visible in the source data)
  ## Notable design choices (bullets: choices that future contributors should know about, drawn from commits or design docs)

Rules:
- Each page is markdown only. No preamble.
- Be concise. The reader is a senior leader scanning, not reading carefully.
- Do not invent facts. If a section has nothing to say from the source data, write `_(no information yet — to be added by the team)_` and move on.
- Do not include citations on stable pages. Citations live on dynamic pages.
- Use the project lead's charter as the most authoritative source for purpose and goals. Augment with what the activity data confirms or hints at, but never contradict the charter.
- Output the page delimiters EXACTLY as shown — no extra spaces, no markdown quoting around them."""


async def write_founding_pages(inputs: PageInputs) -> dict[str, str]:
    """Return `{path: body}` for the four stable pages. Frontmatter applied later."""
    user = (
        f"PROJECT NAME: {inputs.project_name}\n\n"
        f"CHARTER:\n{inputs.charter or '(no charter provided)'}\n\n"
        f"{deltas_block(inputs)}"
    )

    fallback = _stub_response(inputs)
    raw = await call_or_stub(
        page_path="founding-pages",
        system=_SYSTEM_PROMPT,
        user=user,
        fallback=fallback,
        max_tokens=4096,
        temperature=0.3,
    )

    return _split_pages(raw, inputs)


def _split_pages(raw: str, inputs: PageInputs) -> dict[str, str]:
    parts = _SECTION_RE.split(raw)
    # Pattern split yields: [pre, name1, body1, name2, body2, ...]
    pages: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        name = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        pages[name] = body

    # Ensure all four expected stable pages exist; fill missing with stub.
    expected = report_schema.stable_paths()
    if not all(p in pages for p in expected):
        stub = _split_pages(_stub_response(inputs), inputs) if raw is not _stub_response(inputs) else {}
        for p in expected:
            if p not in pages or not pages[p].strip():
                pages[p] = stub.get(p, _empty_stable_body(p, inputs))
    return {p: pages[p] for p in expected}


def _empty_stable_body(path: str, inputs: PageInputs) -> str:
    name = report_schema.SPEC_BY_PATH[path].title if path in report_schema.SPEC_BY_PATH else path
    return f"# {name}\n\n{report_schema.EMPTY_PAGE_PLACEHOLDER}\n"


def _stub_response(inputs: PageInputs) -> str:
    """Deterministic fallback used when the API key is missing."""
    charter = (inputs.charter or "_(no charter provided)_").replace("\n", " ")
    return (
        "===PAGE: overview.md===\n"
        f"## Purpose\n\n{charter}\n\n"
        "## Active goals\n\n_(no goals defined yet — to be added by the team)_\n\n"
        "===PAGE: team.md===\n"
        "## Contributors\n\n_(no contributor info yet)_\n\n"
        "## Stakeholders\n\n_(no stakeholder info yet)_\n\n"
        "===PAGE: glossary.md===\n"
        "_(no glossary entries yet)_\n\n"
        "===PAGE: architecture.md===\n"
        "## Shape\n\n_(no architecture info yet)_\n\n"
        "## Components\n\n_(no components identified yet)_\n"
    )
