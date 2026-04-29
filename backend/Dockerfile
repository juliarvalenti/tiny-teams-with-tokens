FROM python:3.12-slim

# `git` is required by reports/repo.py (we shell out)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pinned uv version matching local dev (0.7.x line)
COPY --from=ghcr.io/astral-sh/uv:0.7.16 /uv /uvx /bin/

WORKDIR /app

# Install deps first (cached unless lockfile changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Then app code
COPY backend ./backend

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/backend" \
    TTT_DB_PATH=/data/ttt.db \
    TTT_REPORT_REPO=/data/reports.git \
    TTT_REPORT_WORKTREE=/data/reports-wc

# Persist DB + report repo across container restarts
VOLUME ["/data"]

EXPOSE 8765

# Backend init (db + bare git repo) is idempotent and runs in the
# FastAPI lifespan, so just launch uvicorn.
CMD ["uvicorn", "ttt.main:app", "--host", "0.0.0.0", "--port", "8765"]
