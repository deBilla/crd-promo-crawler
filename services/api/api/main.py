"""FastAPI application for serving credit card deals."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.config import APIConfig
from api.routes import deals, health
from shared.db import create_engine, create_session_factory, create_tables

logger = logging.getLogger(__name__)
config = APIConfig()

# Module-level engine & session factory (initialized at startup)
engine = create_engine(config.database_url)
session_factory = create_session_factory(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle — startup and shutdown."""
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("Starting API service...")
    await create_tables(engine)
    logger.info("Database ready")
    yield
    await engine.dispose()
    logger.info("API service stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Credit Card Deals API",
        description="API for accessing extracted Sri Lankan credit card deals",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Make session_factory available to route dependencies
    app.state.session_factory = session_factory

    app.include_router(health.router)
    app.include_router(deals.router)

    # Serve frontend dashboard
    # In Docker the package is installed to site-packages, so use STATIC_DIR env or /app/service/static
    static_dir = Path(os.environ.get("STATIC_DIR", "/app/service/static"))
    if not static_dir.is_dir():
        static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/")
        async def serve_dashboard():
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
