import re
from urllib.parse import urlparse, parse_qs
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional

_PKG_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$")


def _clean_package_name(value: str) -> str:
    """Extract package name from a Play Store URL or strip invalid chars."""
    value = value.strip()
    # Accept full Play Store URLs: https://play.google.com/store/apps/details?id=com.example
    if "play.google.com" in value or value.startswith("http"):
        try:
            qs = parse_qs(urlparse(value).query)
            if "id" in qs:
                value = qs["id"][0].strip()
        except Exception:
            pass
    return value


class AppCreate(BaseModel):
    name: str
    package_name: str
    store: str = "google_play"

    @field_validator("package_name")
    @classmethod
    def validate_package_name(cls, v: str) -> str:
        v = _clean_package_name(v)
        if not _PKG_RE.match(v):
            raise ValueError(
                "Invalid package name. Use reverse-domain format (e.g. com.company.app) "
                "or paste the full Play Store URL."
            )
        return v


class AppOut(BaseModel):
    id: int
    name: str
    package_name: str
    store: str
    status: str
    owner_user_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AppUpdate(BaseModel):
    name: Optional[str] = None
    package_name: Optional[str] = None
    status: Optional[str] = None

    @field_validator("package_name")
    @classmethod
    def validate_package_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = _clean_package_name(v)
        if not _PKG_RE.match(v):
            raise ValueError(
                "Invalid package name. Use reverse-domain format (e.g. com.company.app) "
                "or paste the full Play Store URL."
            )
        return v
