"""Add google_play_edit_id to suggestions for soft publish go-live flow.

Revision ID: 010
Revises: 009_add_app_id_to_system_logs
Create Date: 2026-03-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009_add_app_id_to_system_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("suggestions", sa.Column("google_play_edit_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("suggestions", "google_play_edit_id")
