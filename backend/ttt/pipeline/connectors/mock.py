from datetime import datetime
from pathlib import Path

from ttt.pipeline.connectors.base import FetchResult

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"


class MockConnector:
    def __init__(self, name: str, fixture_filename: str) -> None:
        self.name = name
        self._path = FIXTURE_DIR / fixture_filename

    async def fetch(self, *, since: datetime | None = None, **_: object) -> FetchResult:
        if not self._path.exists():
            return FetchResult(
                source=self.name,
                markdown="",
                skipped=True,
                skip_reason=f"fixture missing: {self._path.name}",
            )
        return FetchResult(source=self.name, markdown=self._path.read_text())
