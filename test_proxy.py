"""Quick smoke test: hit the proxy via the ttt anthropic_client wrapper."""

import asyncio
import sys
import os

# Load .env manually so we don't need the full FastAPI stack
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Patch settings before importing the client (it reads env at import time)
import ttt.config as _cfg
_cfg.settings = _cfg.Settings()

from ttt.pipeline import anthropic_client
from ttt.config import settings


async def main():
    print(f"base_url : {settings.anthropic_base_url or '(default anthropic)'}")
    print(f"model    : {settings.extractor_model}")
    print(f"key      : {settings.anthropic_api_key[:8]}...")
    print()

    if not anthropic_client.is_available():
        print("ERROR: ANTHROPIC_API_KEY not set — stub mode only, cannot test proxy.")
        sys.exit(1)

    print("Sending test message...")
    result = await anthropic_client.complete(
        model=settings.extractor_model,
        system="You are a terse assistant.",
        user="Reply with exactly: PROXY_OK",
        max_tokens=16,
        temperature=0.0,
    )
    print(f"Response: {result!r}")

    if "PROXY_OK" in result:
        print("\nSUCCESS — proxy is wired up correctly.")
    else:
        print("\nWARNING — got a response but not the expected echo. Check model/proxy.")


asyncio.run(main())
