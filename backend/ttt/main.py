from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ttt.api import chat, projects, reports, workspace
from ttt.api.mcp_server import mcp
from ttt.db import init_db
from ttt.reports.repo import init_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_store()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Tiny Teams with Tokens", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(workspace.router, prefix="/api")

app.mount("/", mcp.streamable_http_app())


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
