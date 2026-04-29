"""Webex connector — milestone 7. Stub for now.

WARNING: when implemented, the personal access token must NEVER appear in
log output, error messages, or any IngestRun.log content. Use the redaction
filter in pipeline/runner.py.
"""

from datetime import datetime

from ttt.pipeline.connectors.base import FetchResult


class WebexConnector:
    name = "webex"

    def __init__(self, channels: list[str], token: str) -> None:
        self._channels = channels
        self._token = token  # never log this

    async def fetch(self, *, since: datetime | None = None, **_: object) -> FetchResult:
        return FetchResult(
            source=self.name,
            markdown="",
            skipped=True,
            skip_reason="webex connector not implemented (milestone 7)",
        )
