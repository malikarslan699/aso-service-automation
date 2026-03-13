from typing import Optional
from sqlalchemy import String, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, AppScopedMixin


class Keyword(Base, AppScopedMixin, TimestampMixin):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), index=True)
    source: Mapped[str] = mapped_column(String(50), default="")  # competitor, play_suggest, serpapi, manual
    volume_signal: Mapped[float] = mapped_column(Float, default=0.0)
    competition_signal: Mapped[float] = mapped_column(Float, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    cluster: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rank_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, archived
    extra_data: Mapped[str] = mapped_column(Text, default="{}")  # JSON for additional metadata
