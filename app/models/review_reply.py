from typing import Optional
from sqlalchemy import String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, AppScopedMixin


class ReviewReply(Base, AppScopedMixin, TimestampMixin):
    __tablename__ = "review_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[str] = mapped_column(String(200))  # Google Play review ID
    reviewer_name: Mapped[str] = mapped_column(String(200), default="")
    review_text: Mapped[str] = mapped_column(Text, default="")
    review_rating: Mapped[int] = mapped_column(Integer, default=0)
    draft_reply: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, rejected, published
    published_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
