"""PostgreSQL database connection and table definitions.

Uses SQLAlchemy 2.0 async engine with asyncpg driver.
"""

from __future__ import annotations

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# ---------------------------------------------------------------------------
# Engine & Session Factory
# ---------------------------------------------------------------------------


def create_engine(database_url: str, **kwargs) -> AsyncEngine:
    """Create an async SQLAlchemy engine."""
    return create_async_engine(
        database_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        **kwargs,
    )


def create_session_factory(engine: AsyncEngine) -> sessionmaker:
    """Create a session factory bound to the given engine."""
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class URLMetadataRow(Base):
    """Tracks the lifecycle of every URL through the crawl pipeline."""

    __tablename__ = "url_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    domain: Mapped[str] = mapped_column(sa.Text, nullable=False, index=True)
    file_path: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="queued", index=True)
    status_code: Mapped[int | None] = mapped_column(sa.Integer)
    content_hash: Mapped[str | None] = mapped_column(sa.Text)
    depth: Mapped[int] = mapped_column(sa.Integer, default=0)
    retry_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    is_seed: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    discovered_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    fetched_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    parsed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class CreditCardDealRow(Base):
    """A structured credit card promotion extracted by the LLM."""

    __tablename__ = "credit_card_deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    bank_name: Mapped[str] = mapped_column(sa.Text, nullable=False, index=True)
    card_name: Mapped[str | None] = mapped_column(sa.Text)
    card_types: Mapped[list] = mapped_column(sa.JSON, default=list)
    promotion_title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    category: Mapped[str] = mapped_column(sa.Text, default="Other", index=True)
    discount_percentage: Mapped[float | None] = mapped_column(sa.Numeric(5, 2))
    discount_amount: Mapped[float | None] = mapped_column(sa.Numeric(10, 2))
    max_discount_lkr: Mapped[float | None] = mapped_column(sa.Numeric(10, 2))
    merchant_name: Mapped[str | None] = mapped_column(sa.Text)
    merchant_category: Mapped[str | None] = mapped_column(sa.Text)
    merchant_logo_url: Mapped[str | None] = mapped_column(sa.Text)
    valid_days: Mapped[list | None] = mapped_column(sa.JSON)
    valid_from: Mapped[date | None] = mapped_column(sa.Date)
    valid_until: Mapped[date | None] = mapped_column(sa.Date, index=True)
    terms_and_conditions: Mapped[str | None] = mapped_column(sa.Text)
    raw_text: Mapped[str] = mapped_column(sa.Text, default="")
    confidence_score: Mapped[float] = mapped_column(sa.Numeric(3, 2), default=0.0)
    extracted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


# ---------------------------------------------------------------------------
# Table creation helper (for dev / testing — use Alembic in production)
# ---------------------------------------------------------------------------


async def create_tables(engine: AsyncEngine) -> None:
    """Create all tables. Use only for dev/testing — prefer Alembic migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
