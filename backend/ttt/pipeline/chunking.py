"""Hierarchical summarization for large source windows.

Milestone 4 will fill this in. Until then, we just pass markdown through
unchanged. The shape is here so the rest of the pipeline already calls into
it and we only have to swap the implementation.
"""


def maybe_chunk_and_summarize(markdown: str, *, max_chars: int = 60_000) -> str:
    if len(markdown) <= max_chars:
        return markdown
    # TODO milestone 4: split, per-chunk summarize via Haiku, then summarize-of-summaries.
    return markdown[:max_chars] + "\n\n_(truncated — chunker not implemented yet)_"
