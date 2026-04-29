"""Confluence connector — milestone 6. Stub for now."""

from datetime import datetime

from ttt.pipeline.connectors.base import FetchResult


class ConfluenceConnector:
    name = "confluence"

    def __init__(self, roots: list[str], base_url: str, user: str, token: str) -> None:
        self._roots = roots
        self._base_url = base_url
        self._user = user
        self._token = token

    async def fetch(self, *, since: datetime | None = None, **_: object) -> FetchResult:
        return FetchResult(
            source=self.name,
            markdown="",
            skipped=True,
            skip_reason="confluence connector not implemented (milestone 6)",
        )
