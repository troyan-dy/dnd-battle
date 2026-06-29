"""Application factory for the D&D battler backend.

Usage (module-level app is importable by uvicorn):
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.invites import router as invites_router
from app.api.rooms import router as rooms_router
from app.realtime import create_asgi_app


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Registers all routers and middleware here so later tasks can extend
    without touching the entry point (e.g. mount socket.io ASGI sub-app,
    add v1 router, configure CORS, etc.).
    """
    application = FastAPI(
        title="D&D Battler API",
        version="0.1.0",
        description="Authoritative server for the online D&D combat battler.",
    )

    # ---------------------------------------------------------------------------
    # Health probe — liveness/readiness check for infra / CI.
    # Not user-facing text; no i18n needed.
    # ---------------------------------------------------------------------------
    @application.get("/health", tags=["infra"])
    async def health() -> JSONResponse:
        """Return HTTP 200 with {\"status\": \"ok\"} to signal the server is up."""
        return JSONResponse(content={"status": "ok"})

    # ---------------------------------------------------------------------------
    # Domain routers.
    # ---------------------------------------------------------------------------
    application.include_router(rooms_router)
    application.include_router(invites_router)

    # ---------------------------------------------------------------------------
    # Future: include versioned API routers, add CORS middleware.
    # ---------------------------------------------------------------------------

    return application


# Module-level FastAPI instance (importable for HTTP-only tests / sub-mounting).
fastapi_app = create_app()

# Module-level ASGI instance so `uvicorn app.main:app` serves BOTH the REST API
# and the realtime `/socket.io` endpoint from one process. Socket.IO requests are
# handled by the AsyncServer; everything else falls through to FastAPI.
app: Any = create_asgi_app(fastapi_app)
