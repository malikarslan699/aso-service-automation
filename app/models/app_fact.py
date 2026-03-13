from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, AppScopedMixin


class AppFact(Base, AppScopedMixin, TimestampMixin):
    __tablename__ = "app_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    fact_key: Mapped[str] = mapped_column(String(100))  # encryption_type, kill_switch, etc.
    fact_value: Mapped[str] = mapped_column(String(500))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
