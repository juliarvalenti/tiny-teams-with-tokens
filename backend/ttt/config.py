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
    # Filesystem cache mirroring the latest page state — sqlite is authoritative.
    # The chat agent's Read/Edit/Write tools operate on these files directly.
    ttt_wiki_dir: Path = _PROJECT_ROOT / "data" / "wiki"

    extractor_model: str = "claude-haiku-4-5"
    synthesizer_model: str = "claude-haiku-4-5"  # PoC: cheapest tier; bump to opus later for quality

    # "static" = the original fan-out pipeline (extractors + page synthesizers).
    # "agent"  = Claude Agent SDK loop with in-process GitHub MCP. Cheaper to
    #           reason about, easier to extend (#13 backlinks, #8 team), but
    #           less deterministic per ingest.
    ingest_mode: str = "static"


settings = Settings()
