"""FastAPI entrypoint."""

import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import jwt as pyjwt

from .config import get_settings
from .graph.builder import build_graph, close_graph
from .mcp_server.context import set_user_id
from .mcp_server.server import build_mcp_server, expected_token
from .routes import (
    audit,
    chat,
    jobs,
    mcp_connections,
    notes,
    oauth,
    onboarding,
    skills,
    status as status_routes,
    tasks,
    voice,
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Langsmith — LangChain reads these from env at import time, but we set them
    # here too so .env values flow through pydantic-settings.
    if settings.langsmith_tracing and settings.langsmith_api_key:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
        log.info("langsmith.enabled", project=settings.langsmith_project)

    log.info("jai.starting", model_orchestrator=settings.jai_model_orchestrator)
    app.state.graph = await build_graph(settings)
    try:
        yield
    finally:
        await close_graph(app.state.graph)
        log.info("jai.stopped")


app = FastAPI(
    title="JAI API",
    version="0.1.0",
    description="Second brain, founder OS, autonomous operator.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(voice.router, prefix="/voice", tags=["voice"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(notes.router, prefix="/notes", tags=["notes"])
app.include_router(skills.router, prefix="/skills", tags=["skills"])
app.include_router(mcp_connections.router, prefix="/mcp/connections", tags=["mcp"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(oauth.router, prefix="/auth", tags=["auth"])
app.include_router(audit.router, prefix="/audit", tags=["audit"])
app.include_router(status_routes.router, prefix="/status", tags=["status"])
app.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])


@app.get("/health")
async def health():
    return {"ok": True, "service": "jai-api"}


# --- Internal MCP server (mounted at /mcp/sse). ---
# Auth accepts two flavors:
#   1) Bearer <JAI_MCP_SERVER_TOKEN>   → single-tenant, uses JAI_USER_ID
#   2) Bearer <Supabase JWT>           → multi-tenant, uses sub claim
# Both set the contextvar so each tool call is scoped to one user.
_internal_mcp = build_mcp_server()
if _internal_mcp is not None:
    @app.middleware("http")
    async def _mcp_auth(request: Request, call_next):
        path = request.url.path
        if path.startswith("/mcp/sse"):
            got = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            settings = get_settings()
            user_id: str | None = None

            tok = expected_token()
            if tok and got == tok:
                user_id = settings.jai_user_id or None
            else:
                # Try Supabase JWT
                if settings.supabase_jwt_secret and got:
                    try:
                        claims = pyjwt.decode(
                            got,
                            settings.supabase_jwt_secret,
                            algorithms=["HS256"],
                            audience="authenticated",
                        )
                        user_id = claims.get("sub")
                    except pyjwt.PyJWTError:
                        user_id = None

            if not user_id:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            set_user_id(user_id)
        return await call_next(request)

    app.mount("/mcp/sse", _internal_mcp.sse_app())
