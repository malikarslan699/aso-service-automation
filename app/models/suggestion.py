from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, AppScopedMixin


class Suggestion(Base, AppScopedMixin, TimestampMixin):
    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    suggestion_type: Mapped[str] = mapped_column(String(30))  # title, short_desc, long_desc, review_reply
    field_name: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    risk_score: Mapped[int] = mapped_column(Integer, default=0)  # 0-5
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, rejected, published, rolled_back
    safety_result: Mapped[str] = mapped_column(Text, default="")  # JSON: layer results
    extra_data: Mapped[str] = mapped_column(Text, default="{}")  # JSON metadata (e.g. review_id)
    pipeline_run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    publish_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    publish_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publish_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    publish_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_live: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dry_run_result: Mapped[bool] = mapped_column(Boolean, default=False)
    last_transition_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    merged_into_job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dispatch_window: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    next_eligible_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    publish_block_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
