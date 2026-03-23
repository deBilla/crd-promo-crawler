"""Deal CRUD routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import DealListResponse, DealResponse
from shared.db import CreditCardDealRow

router = APIRouter(prefix="/deals", tags=["deals"])


async def get_session(request: Request):
    """Dependency: yield an async DB session from the app's session factory."""
    async with request.app.state.session_factory() as session:
        yield session


@router.get("", response_model=DealListResponse)
async def list_deals(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    bank_name: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    merchant_category: Optional[str] = Query(None),
    active_only: bool = Query(False),
    session: AsyncSession = Depends(get_session),
) -> DealListResponse:
    """List credit card deals with optional filters."""
    query = select(CreditCardDealRow)
    count_query = select(func.count()).select_from(CreditCardDealRow)

    # Apply filters
    if bank_name:
        query = query.where(CreditCardDealRow.bank_name.ilike(f"%{bank_name}%"))
        count_query = count_query.where(CreditCardDealRow.bank_name.ilike(f"%{bank_name}%"))
    if category:
        query = query.where(CreditCardDealRow.category.ilike(f"%{category}%"))
        count_query = count_query.where(CreditCardDealRow.category.ilike(f"%{category}%"))
    if merchant_category:
        query = query.where(CreditCardDealRow.merchant_category.ilike(f"%{merchant_category}%"))
        count_query = count_query.where(CreditCardDealRow.merchant_category.ilike(f"%{merchant_category}%"))
    if active_only:
        query = query.where(CreditCardDealRow.valid_until >= datetime.utcnow().date())
        count_query = count_query.where(CreditCardDealRow.valid_until >= datetime.utcnow().date())

    total = await session.scalar(count_query)

    offset = (page - 1) * per_page
    query = query.order_by(CreditCardDealRow.id.desc()).offset(offset).limit(per_page)

    result = await session.execute(query)
    deals = result.scalars().all()

    return DealListResponse(
        deals=[DealResponse.model_validate(d) for d in deals],
        total=total or 0,
        page=page,
        per_page=per_page,
    )


@router.get("/stats")
async def get_stats(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get statistics about deals in the database."""
    bank_counts = await session.execute(
        select(
            CreditCardDealRow.bank_name,
            func.count(CreditCardDealRow.id).label("count"),
        ).group_by(CreditCardDealRow.bank_name)
    )
    banks = {row[0]: row[1] for row in bank_counts.all()}

    category_counts = await session.execute(
        select(
            CreditCardDealRow.category,
            func.count(CreditCardDealRow.id).label("count"),
        ).group_by(CreditCardDealRow.category)
    )
    categories = {row[0]: row[1] for row in category_counts.all()}

    total = await session.scalar(select(func.count(CreditCardDealRow.id)))

    return {
        "total_deals": total or 0,
        "by_bank": banks,
        "by_category": categories,
    }


@router.get("/search", response_model=DealListResponse)
async def search_deals(
    keyword: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> DealListResponse:
    """Search deals by keyword in title and description."""
    base_filter = (
        (CreditCardDealRow.promotion_title.ilike(f"%{keyword}%"))
        | (CreditCardDealRow.description.ilike(f"%{keyword}%"))
    )

    count_query = select(func.count()).select_from(CreditCardDealRow).where(base_filter)
    total = await session.scalar(count_query)

    offset = (page - 1) * per_page
    query = (
        select(CreditCardDealRow)
        .where(base_filter)
        .order_by(CreditCardDealRow.id.desc())
        .offset(offset)
        .limit(per_page)
    )

    result = await session.execute(query)
    deals = result.scalars().all()

    return DealListResponse(
        deals=[DealResponse.model_validate(d) for d in deals],
        total=total or 0,
        page=page,
        per_page=per_page,
    )


@router.get("/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal_id: int,
    session: AsyncSession = Depends(get_session),
) -> DealResponse:
    """Get a single deal by ID."""
    result = await session.execute(
        select(CreditCardDealRow).where(CreditCardDealRow.id == deal_id)
    )
    deal = result.scalar_one_or_none()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    return DealResponse.model_validate(deal)
