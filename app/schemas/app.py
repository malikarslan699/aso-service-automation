from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AppCreate(BaseModel):
    name: str
    package_name: str
    store: str = "google_play"


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
    status: Optional[str] = None
