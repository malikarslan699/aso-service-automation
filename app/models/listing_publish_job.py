from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppScopedMixin, Base, TimestampMixin


class ListingPublishJob(Base, AppScopedMixin, TimestampMixin):
    __tablename__ = "listing_publish_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(40), default="listing_bundle")
    status: Mapped[str] = mapped_column(String(40), default="queued_bundle")
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)

    title_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    short_description_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    long_description_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggestion_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of suggestion IDs

    dispatch_window: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    jitter_seconds: Mapped[int] = mapped_column(Integer, default=0)
    min_gap_minutes: Mapped[int] = mapped_column(Integer, default=60)
    next_eligible_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
