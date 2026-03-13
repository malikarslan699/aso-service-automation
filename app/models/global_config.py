from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class GlobalConfig(Base, TimestampMixin):
    __tablename__ = "global_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[str] = mapped_column(Text, default="")  # encrypted
    description: Mapped[str] = mapped_column(String(300), default="")
