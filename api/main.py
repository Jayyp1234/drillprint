"""FastAPI application — OpenAPI metadata, dual-serve CORS (A13/A14)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.app_state import AppState
from api.routes_bench import router as bench_router
from api.routes_library import router as library_router
from api.routes_stream import router as stream_router

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "library.db"
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend_dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = AppState(db_path=app.state.db_path)
    state.loop = asyncio.get_running_loop()
    app.state.dp = state
    yield
    state.close()


def create_app(db_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(
        title="DrillPrint",
        version="0.1.0",
        description="Deterministic spectral fingerprinting for drilling dysfunction",
        lifespan=lifespan,
    )
    app.state.db_path = Path(db_path) if db_path else DEFAULT_DB
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(library_router)
    app.include_router(stream_router)
    app.include_router(bench_router)

    @app.get("/health")
    def health():
        dp: AppState = app.state.dp
        return {
            "ok": True,
            "active_library": dp.db.active_version() if dp.db else None,
            "ingest": dp.engine.session.health.as_dict() if dp.engine else {},
            "monitor_subscribers": len(dp.subscribers),
        }

    @app.get("/scenarios")
    def scenarios():
        root = Path(__file__).resolve().parent.parent / "scenarios"
        if not root.exists():
            return []
        return sorted(p.stem for p in root.glob("*.json"))

    # Dual-serve: API + committed UI build (A13 / §33)
    if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "index.html").exists():
        assets = FRONTEND_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}")
        async def spa(full_path: str):
            candidate = FRONTEND_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
