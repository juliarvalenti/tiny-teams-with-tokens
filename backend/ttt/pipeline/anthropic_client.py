"""Thin wrapper around the Anthropic Messages API.

- Lazy singleton client (so import doesn't require an API key).
- Async retry-with-backoff for transient errors.
- `is_available()` to gate real calls on the env having a key.
"""

from __future__ import annotations

import asyncio
import logging

import anthropic
from anthropic import AsyncAnthropic

from ttt.config import settings

log = logging.getLogger("ttt.anthropic")

_client: AsyncAnthropic | None = None


def is_available() -> bool:
    return bool(settings.anthropic_api_key)


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; cannot make Messages API calls."
            )
        kwargs: dict = {"api_key": settings.anthropic_api_key}
        if settings.anthropic_base_url:
            kwargs["base_url"] = settings.anthropic_base_url
        _client = AsyncAnthropic(**kwargs)
    return _client


async def complete(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    max_retries: int = 4,
) -> str:
    """Send a single (system, user) Messages API call and return the text body.

    Retries on RateLimitError + 5xx APIStatusError with exponential backoff.
    """
    client = _get_client()
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            # Concatenate text blocks — most responses are a single block.
            parts: list[str] = []
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    parts.append(block.text)
            return "".join(parts).strip()
        except anthropic.RateLimitError as e:
            last_exc = e
            log.warning("rate limited (attempt %d/%d): %s", attempt + 1, max_retries, e)
        except anthropic.APIStatusError as e:
            if 500 <= e.status_code < 600:
                last_exc = e
                log.warning(
                    "5xx from anthropic (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
            else:
                raise
        await asyncio.sleep(delay)
        delay *= 2
    assert last_exc is not None
    raise last_exc
