"""API response schemas."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class DealResponse(BaseModel):
    """Response model for a single credit card deal."""

    id: int
    source_url: str
    bank_name: str
    card_name: Optional[str] = None
    card_types: list[str] = []
    promotion_title: str
    description: str
    category: str
    discount_percentage: Optional[float] = None
    discount_amount: Optional[float] = None
    max_discount_lkr: Optional[float] = None
    merchant_name: Optional[str] = None
    merchant_category: Optional[str] = None
    merchant_logo_url: Optional[str] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    valid_days: Optional[list[str]] = None
    terms_and_conditions: Optional[str] = None
    confidence_score: float = 0.0
    extracted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DealListResponse(BaseModel):
    """Response model for a paginated list of deals."""

    deals: list[DealResponse]
    total: int
    page: int
    per_page: int


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    database: str
