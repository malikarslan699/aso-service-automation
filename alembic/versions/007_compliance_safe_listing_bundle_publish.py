"""Add listing bundle publish jobs and suggestion dispatch metadata

Revision ID: 007
Revises: 006
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_publish_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False, server_default="listing_bundle"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued_bundle"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("title_value", sa.Text(), nullable=True),
        sa.Column("short_description_value", sa.Text(), nullable=True),
        sa.Column("long_description_value", sa.Text(), nullable=True),
        sa.Column("suggestion_ids", sa.Text(), nullable=True),
        sa.Column("dispatch_window", sa.String(length=120), nullable=True),
        sa.Column("jitter_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("min_gap_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("next_eligible_at", sa.DateTime(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_listing_publish_jobs_app_id"), "listing_publish_jobs", ["app_id"], unique=False)

    with op.batch_alter_table("suggestions") as batch_op:
        batch_op.add_column(sa.Column("merged_into_job_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("dispatch_window", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("next_eligible_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("publish_block_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("suggestions") as batch_op:
        batch_op.drop_column("publish_block_reason")
        batch_op.drop_column("next_eligible_at")
        batch_op.drop_column("dispatch_window")
        batch_op.drop_column("merged_into_job_id")

    op.drop_index(op.f("ix_listing_publish_jobs_app_id"), table_name="listing_publish_jobs")
    op.drop_table("listing_publish_jobs")
