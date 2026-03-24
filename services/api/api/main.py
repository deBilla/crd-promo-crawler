"""FastAPI application for serving credit card deals."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
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

# Telemetry instruments (initialized at startup)
_meter = None
_tracer = None
_api_requests = None
_api_request_duration = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle — startup and shutdown."""
    global _meter, _tracer, _api_requests, _api_request_duration

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Initialize OpenTelemetry
    if config.otel_enabled:
        from shared.telemetry import init_telemetry
        _meter, _tracer = init_telemetry("api", config.otel_endpoint)
        _api_requests = _meter.create_counter(
            "api_requests", description="API requests by endpoint/method/status",
        )
        _api_request_duration = _meter.create_histogram(
            "api_request_duration_seconds", description="API response time", unit="s",
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

    # Metrics middleware
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        t0 = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - t0
        endpoint = request.url.path
        method = request.method
        status = str(response.status_code)
        if _api_requests:
            _api_requests.add(1, {"endpoint": endpoint, "method": method, "status": status})
        if _api_request_duration:
            _api_request_duration.record(duration, {"endpoint": endpoint, "method": method})
        return response

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
