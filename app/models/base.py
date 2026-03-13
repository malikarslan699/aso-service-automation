from datetime import datetime
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class AppScopedMixin:
    """Mixin for all tables scoped to a specific app."""

    @declared_attr
    def app_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)
