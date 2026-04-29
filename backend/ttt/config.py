from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""

    github_token: str = ""
    confluence_base_url: str = ""
    confluence_user: str = ""
    confluence_token: str = ""
    webex_token: str = ""

    ttt_db_path: Path = Path("./data/ttt.db")
    ttt_report_repo: Path = Path("./data/reports.git")
    ttt_report_worktree: Path = Path("./data/reports-wc")

    extractor_model: str = "claude-haiku-4-5"
    synthesizer_model: str = "claude-haiku-4-5"  # PoC: cheapest tier; bump to opus later for quality


settings = Settings()
