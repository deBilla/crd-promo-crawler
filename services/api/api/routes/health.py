"""Health check route."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import HealthResponse

router = APIRouter(tags=["health"])


async def get_session(request: Request):
    """Dependency: yield an async DB session from the app's session factory."""
    async with request.app.state.session_factory() as session:
        yield session


@router.get("/health", response_model=HealthResponse)
async def health_check(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    """Check API and database health."""
    try:
        await session.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception as e:
        database_status = f"error: {str(e)}"

    return HealthResponse(status="ok", database=database_status)
