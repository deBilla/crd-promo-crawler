from pydantic import BaseModel, Field, ValidationError, validator
from typing import List, Optional, Literal
import datetime

# --- Canonical Lists for Validation ---
CANONICAL_CATEGORIES = [
    "Dining & Restaurants", "Shopping & Retail", "Travel & Lodging",
    "Health & Wellness", "Groceries & Supermarkets", "Online Shopping",
    "Fuel", "Other"
]
VALID_CARD_TYPES = [
    "Credit Card", "Debit Card", "Visa", "Mastercard", "Amex"
]

# --- Nested Pydantic Models for a Clean Schema ---

class Merchant(BaseModel):
    name: str
    logo_url: Optional[str] = None

class OfferDetails(BaseModel):
    type: Literal["percentage", "fixed_amount", "buy_one_get_one", "other"]
    value: Optional[float] = None
    max_discount_lkr: Optional[int] = None

class Validity(BaseModel):
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    days: Optional[List[str]] = None

# --- Main Promotion Model ---

class Promotion(BaseModel):
    id: Optional[str] = None # Will be assigned later
    bank: str
    card_types: List[str]
    category: str
    merchant: Merchant
    title: str
    description: str
    offer_details: OfferDetails
    validity: Validity
    terms: Optional[str] = None
    source_url: str

    # Pydantic can run validators on the data after parsing
    @validator('category')
    def category_must_be_in_canonical_list(cls, v):
        if v not in CANONICAL_CATEGORIES:
            # Instead of crashing, let's default to 'Other' and log it later if needed.
            # This makes the pipeline more resilient to unexpected AI output.
            return "Other" 
        return v