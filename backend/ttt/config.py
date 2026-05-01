from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor relative paths and the .env lookup at the project root regardless of
# where the process was launched. Without this, running uvicorn from a child
# directory silently splits state into a separate sqlite db / git repo.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_PROJECT_ROOT / ".env"), extra="ignore")

    anthropic_api_key: str = ""
    anthropic_base_url: str = ""  # set to proxy URL e.g. http://localhost:8099

    github_token: str = ""
    confluence_base_url: str = ""
    confluence_user: str = ""
    confluence_token: str = ""
    webex_token: str = ""

    ttt_db_path: Path = _PROJECT_ROOT / "data" / "ttt.db"
    ttt_report_repo: Path = _PROJECT_ROOT / "data" / "reports.git"
    ttt_report_worktree: Path = _PROJECT_ROOT / "data" / "reports-wc"

    extractor_model: str = "claude-haiku-4-5"
    synthesizer_model: str = "claude-haiku-4-5"  # PoC: cheapest tier; bump to opus later for quality


settings = Settings()
