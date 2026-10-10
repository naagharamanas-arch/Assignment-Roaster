"""Track the usage date charged to a submission so refunds hit the right counter

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("usage_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("submissions", "usage_date")
