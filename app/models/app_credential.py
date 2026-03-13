from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, AppScopedMixin


class AppCredential(Base, AppScopedMixin, TimestampMixin):
    __tablename__ = "app_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    credential_type: Mapped[str] = mapped_column(String(50))  # service_account_json, api_key
    value: Mapped[str] = mapped_column(Text)  # encrypted
