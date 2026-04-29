from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class FetchResult:
    """Pre-fetched, pre-flattened source data ready for an extractor agent."""

    source: str  # "github" | "confluence" | "webex" | "mock"
    markdown: str  # the actual content the extractor will read
    skipped: bool = False
    skip_reason: str = ""


class Connector(Protocol):
    name: str

    async def fetch(self, *, since: datetime | None, **kwargs: object) -> FetchResult:
        ...
