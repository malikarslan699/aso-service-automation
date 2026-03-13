from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class PolicyCache(Base, TimestampMixin):
    __tablename__ = "policy_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_type: Mapped[str] = mapped_column(String(100), unique=True)  # vpn_policy, metadata_policy
    content: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(500), default="")
