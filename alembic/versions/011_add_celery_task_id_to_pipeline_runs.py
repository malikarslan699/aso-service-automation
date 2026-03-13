"""Add celery_task_id to pipeline_runs for cancel support.

Revision ID: 011
Revises: 010
Create Date: 2026-03-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pipeline_runs",
        sa.Column("celery_task_id", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "celery_task_id")
