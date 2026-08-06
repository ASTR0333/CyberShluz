"""add a separate unprivileged SSH key to stands

Revision ID: c31d92e147ad
Revises: 89a17b25959f
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c31d92e147ad"
down_revision: Union[str, None] = "89a17b25959f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stands", sa.Column("student_private_key", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("stands", "student_private_key")
