from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, Float, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, AppScopedMixin


class PipelineRun(Base, AppScopedMixin, TimestampMixin):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="running")  # queued, running, completed, completed_with_warnings, failed, skipped, blocked
    trigger: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled, manual
    steps_completed: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=9)
    suggestions_generated: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0)
    keywords_discovered: Mapped[int] = mapped_column(Integer, default=0)
    approvals_created: Mapped[int] = mapped_column(Integer, default=0)
    provider_name: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    fallback_provider_name: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    provider_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    provider_error_class: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    value_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    step_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
