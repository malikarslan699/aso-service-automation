"""Initial schema - all 14 tables

Revision ID: 001
Revises:
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # apps
    op.create_table(
        "apps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("package_name", sa.String(200), nullable=False, unique=True),
        sa.Column("store", sa.String(20), server_default="google_play"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("email", sa.String(200), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), server_default="admin"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # global_config
    op.create_table(
        "global_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("value", sa.Text(), server_default=""),
        sa.Column("description", sa.String(300), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # policy_cache (global, no app_id)
    op.create_table(
        "policy_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_type", sa.String(100), nullable=False, unique=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(500), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # system_logs (global, no app_id)
    op.create_table(
        "system_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("module", sa.String(100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # app_credentials (app_id FK)
    op.create_table(
        "app_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("credential_type", sa.String(50), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # suggestions
    op.create_table(
        "suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("suggestion_type", sa.String(30), nullable=False),
        sa.Column("field_name", sa.String(50), nullable=False),
        sa.Column("old_value", sa.Text(), server_default=""),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("reasoning", sa.Text(), server_default=""),
        sa.Column("risk_score", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("safety_result", sa.Text(), server_default=""),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # app_listings
    op.create_table(
        "app_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(50), server_default=""),
        sa.Column("short_description", sa.String(80), server_default=""),
        sa.Column("long_description", sa.Text(), server_default=""),
        sa.Column("snapshot_type", sa.String(20), server_default="daily"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # keywords
    op.create_table(
        "keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("keyword", sa.String(200), nullable=False, index=True),
        sa.Column("source", sa.String(50), server_default=""),
        sa.Column("volume_signal", sa.Float(), server_default="0"),
        sa.Column("competition_signal", sa.Float(), server_default="0"),
        sa.Column("opportunity_score", sa.Float(), server_default="0"),
        sa.Column("cluster", sa.String(100), nullable=True),
        sa.Column("rank_position", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("extra_data", sa.Text(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # pipeline_runs
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("trigger", sa.String(20), server_default="scheduled"),
        sa.Column("steps_completed", sa.Integer(), server_default="0"),
        sa.Column("total_steps", sa.Integer(), server_default="9"),
        sa.Column("suggestions_generated", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # review_replies
    op.create_table(
        "review_replies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("review_id", sa.String(200), nullable=False),
        sa.Column("reviewer_name", sa.String(200), server_default=""),
        sa.Column("review_text", sa.Text(), server_default=""),
        sa.Column("review_rating", sa.Integer(), server_default="0"),
        sa.Column("draft_reply", sa.Text(), server_default=""),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("published_reply", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # app_facts
    op.create_table(
        "app_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("fact_key", sa.String(100), nullable=False),
        sa.Column("fact_value", sa.String(500), nullable=False),
        sa.Column("verified", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # auto_approve_rules
    op.create_table(
        "auto_approve_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("suggestion_type", sa.String(30), nullable=False),
        sa.Column("max_risk_score", sa.Integer(), server_default="1"),
        sa.Column("approved_count", sa.Integer(), server_default="0"),
        sa.Column("rejected_count", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # notifications
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("notification_type", sa.String(30), server_default="info"),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("auto_approve_rules")
    op.drop_table("app_facts")
    op.drop_table("review_replies")
    op.drop_table("pipeline_runs")
    op.drop_table("keywords")
    op.drop_table("app_listings")
    op.drop_table("suggestions")
    op.drop_table("app_credentials")
    op.drop_table("system_logs")
    op.drop_table("policy_cache")
    op.drop_table("global_config")
    op.drop_table("users")
    op.drop_table("apps")
