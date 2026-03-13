from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, AppScopedMixin


class AutoApproveRule(Base, AppScopedMixin, TimestampMixin):
    __tablename__ = "auto_approve_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    suggestion_type: Mapped[str] = mapped_column(String(30))  # review_reply, short_desc, etc.
    max_risk_score: Mapped[int] = mapped_column(Integer, default=1)
    approved_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=False)
