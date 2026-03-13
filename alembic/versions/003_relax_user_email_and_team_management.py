"""Relax user email uniqueness and support team management

Revision ID: 003
Revises: 002
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(length=200), nullable=True)
        batch_op.drop_constraint("users_email_key", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.create_unique_constraint("users_email_key", ["email"])
        batch_op.alter_column("email", existing_type=sa.String(length=200), nullable=False)
