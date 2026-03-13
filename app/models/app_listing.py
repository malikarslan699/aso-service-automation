from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, AppScopedMixin


class AppListing(Base, AppScopedMixin, TimestampMixin):
    __tablename__ = "app_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(50), default="")
    short_description: Mapped[str] = mapped_column(String(80), default="")
    long_description: Mapped[str] = mapped_column(Text, default="")
    snapshot_type: Mapped[str] = mapped_column(String(20), default="daily")  # daily, before_publish, after_publish
