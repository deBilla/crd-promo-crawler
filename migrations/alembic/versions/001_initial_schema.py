"""Initial schema — url_metadata and credit_card_deals tables.

Revision ID: 001
Revises: None
Create Date: 2026-03-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "url_metadata",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("url", sa.Text, nullable=False, unique=True),
        sa.Column("domain", sa.Text, nullable=False),
        sa.Column("file_path", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("status_code", sa.Integer),
        sa.Column("content_hash", sa.Text),
        sa.Column("depth", sa.Integer, server_default="0"),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("is_seed", sa.Boolean, server_default="false"),
        sa.Column("error_message", sa.Text),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("parsed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_url_metadata_domain", "url_metadata", ["domain"])
    op.create_index("idx_url_metadata_status", "url_metadata", ["status"])

    op.create_table(
        "credit_card_deals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("bank_name", sa.Text, nullable=False),
        sa.Column("card_name", sa.Text),
        sa.Column("card_types", sa.JSON, server_default="[]"),
        sa.Column("promotion_title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.Text, server_default="'Other'"),
        sa.Column("discount_percentage", sa.Numeric(5, 2)),
        sa.Column("discount_amount", sa.Numeric(10, 2)),
        sa.Column("max_discount_lkr", sa.Numeric(10, 2)),
        sa.Column("merchant_name", sa.Text),
        sa.Column("merchant_category", sa.Text),
        sa.Column("merchant_logo_url", sa.Text),
        sa.Column("valid_days", sa.JSON),
        sa.Column("valid_from", sa.Date),
        sa.Column("valid_until", sa.Date),
        sa.Column("terms_and_conditions", sa.Text),
        sa.Column("raw_text", sa.Text, server_default="''"),
        sa.Column("confidence_score", sa.Numeric(3, 2), server_default="0"),
        sa.Column("extracted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_deals_bank", "credit_card_deals", ["bank_name"])
    op.create_index("idx_deals_category", "credit_card_deals", ["category"])
    op.create_index("idx_deals_valid_until", "credit_card_deals", ["valid_until"])


def downgrade() -> None:
    op.drop_table("credit_card_deals")
    op.drop_table("url_metadata")
