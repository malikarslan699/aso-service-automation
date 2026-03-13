"""Add user app access and manual approval workflow settings

Revision ID: 002
Revises: 001
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_app_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "app_id", name="uq_user_app_access_user_app"),
    )
    op.create_index("ix_user_app_access_user_id", "user_app_access", ["user_id"])
    op.create_index("ix_user_app_access_app_id", "user_app_access", ["app_id"])


def downgrade() -> None:
    op.drop_index("ix_user_app_access_app_id", table_name="user_app_access")
    op.drop_index("ix_user_app_access_user_id", table_name="user_app_access")
    op.drop_table("user_app_access")
