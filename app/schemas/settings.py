from pydantic import BaseModel
from typing import Optional


class GlobalConfigOut(BaseModel):
    key: str
    value: str  # masked for secrets
    description: str

    model_config = {"from_attributes": True}


class GlobalConfigUpdate(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


class AppSettingsOut(BaseModel):
    dry_run: bool
    max_publish_per_day: int
    max_publish_per_week: int
    auto_approve_threshold: int
