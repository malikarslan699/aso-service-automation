"""Add project ownership and pipeline analytics

Revision ID: 005
Revises: 004
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("apps") as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_apps_owner_user_id", ["owner_user_id"], unique=False)
        batch_op.create_foreign_key("fk_apps_owner_user_id_users", "users", ["owner_user_id"], ["id"], ondelete="SET NULL")

    with op.batch_alter_table("pipeline_runs") as batch_op:
        batch_op.alter_column("status", existing_type=sa.String(length=20), type_=sa.String(length=32), existing_nullable=False)
        batch_op.add_column(sa.Column("keywords_discovered", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("approvals_created", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("provider_name", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("fallback_provider_name", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("provider_status", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("provider_error_class", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("value_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("step_log", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pipeline_runs") as batch_op:
        batch_op.drop_column("step_log")
        batch_op.drop_column("value_summary")
        batch_op.drop_column("estimated_cost")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
        batch_op.drop_column("provider_error_class")
        batch_op.drop_column("provider_status")
        batch_op.drop_column("fallback_provider_name")
        batch_op.drop_column("provider_name")
        batch_op.drop_column("approvals_created")
        batch_op.drop_column("keywords_discovered")
        batch_op.alter_column("status", existing_type=sa.String(length=32), type_=sa.String(length=20), existing_nullable=False)

    with op.batch_alter_table("apps") as batch_op:
        batch_op.drop_constraint("fk_apps_owner_user_id_users", type_="foreignkey")
        batch_op.drop_index("ix_apps_owner_user_id")
        batch_op.drop_column("owner_user_id")
