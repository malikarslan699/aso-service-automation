"""Add suggestion publish visibility fields

Revision ID: 006
Revises: 005
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("suggestions") as batch_op:
        batch_op.add_column(sa.Column("publish_status", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("publish_message", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("publish_started_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("publish_completed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("published_live", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("is_dry_run_result", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("last_transition_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("status_log", sa.Text(), nullable=True))

    op.execute("UPDATE suggestions SET published_live = TRUE WHERE status = 'published'")


def downgrade() -> None:
    with op.batch_alter_table("suggestions") as batch_op:
        batch_op.drop_column("status_log")
        batch_op.drop_column("last_transition_at")
        batch_op.drop_column("is_dry_run_result")
        batch_op.drop_column("published_live")
        batch_op.drop_column("publish_completed_at")
        batch_op.drop_column("publish_started_at")
        batch_op.drop_column("publish_message")
        batch_op.drop_column("publish_status")
