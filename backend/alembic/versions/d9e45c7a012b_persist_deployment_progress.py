"""persist deployment progress independently of the Celery result backend

Revision ID: d9e45c7a012b
Revises: c31d92e147ad
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9e45c7a012b"
down_revision: Union[str, None] = "c31d92e147ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stands", sa.Column("deployment_progress", sa.Integer(), nullable=True))
    op.add_column("stands", sa.Column("deployment_message", sa.Text(), nullable=True))
    op.add_column("stands", sa.Column("deployment_error", sa.Text(), nullable=True))
    op.add_column("stands", sa.Column("deployment_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("stands", "deployment_updated_at")
    op.drop_column("stands", "deployment_error")
    op.drop_column("stands", "deployment_message")
    op.drop_column("stands", "deployment_progress")
