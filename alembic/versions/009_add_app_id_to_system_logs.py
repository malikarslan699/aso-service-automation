"""Add app_id to system_logs for project-scoped visibility.

Revision ID: 009_add_app_id_to_system_logs
Revises: 008_suggestion_extra_data_and_review_reply_guard
Create Date: 2026-03-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009_add_app_id_to_system_logs"
down_revision: Union[str, None] = "008_suggestion_extra_data_and_review_reply_guard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("system_logs", sa.Column("app_id", sa.Integer(), nullable=True))
    op.create_index("ix_system_logs_app_id", "system_logs", ["app_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_system_logs_app_id", table_name="system_logs")
    op.drop_column("system_logs", "app_id")
