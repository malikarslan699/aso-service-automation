"""Add suggestion extra_data and block unsafe legacy review replies.

Revision ID: 008
Revises: 007
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("suggestions") as batch_op:
        batch_op.add_column(sa.Column("extra_data", sa.Text(), nullable=False, server_default="{}"))

    # Legacy review-reply items were created without review_id metadata.
    # Block them explicitly so background workers do not call Google APIs with invalid paths.
    op.execute(
        """
        UPDATE suggestions
        SET
            publish_status = 'blocked',
            publish_message = '[missing_review_id] Review reply is missing review_id metadata. Regenerate this suggestion from a new pipeline run.',
            publish_block_reason = '[missing_review_id] Review reply is missing review_id metadata. Regenerate this suggestion from a new pipeline run.',
            last_transition_at = CURRENT_TIMESTAMP
        WHERE suggestion_type = 'review_reply'
          AND status IN ('pending', 'approved')
          AND (extra_data IS NULL OR TRIM(extra_data) = '' OR TRIM(extra_data) = '{}' OR extra_data NOT LIKE '%"review_id"%')
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("suggestions") as batch_op:
        batch_op.drop_column("extra_data")
