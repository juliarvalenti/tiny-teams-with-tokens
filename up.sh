#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Install deps if needed
uv sync --group dev
(cd frontend && npm ci)

# Init DB if missing
[ -f data/ttt.db ] || uv run ttt init-data

# Start backend
INGEST_MODE=agent uv run uvicorn ttt.main:app --port 8765 \
  --reload --reload-dir backend/ttt &
BACKEND_PID=$!

# Start frontend
(cd frontend && npm run dev -- -p 3001) &
FRONTEND_PID=$!

echo "backend PID $BACKEND_PID, frontend PID $FRONTEND_PID"
echo "backend:  http://localhost:8765"
echo "frontend: http://localhost:3001"

wait
