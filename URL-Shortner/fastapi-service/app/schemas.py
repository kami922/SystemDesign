from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LinkCreateRequest(BaseModel):
    long_url: str
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None


class LinkResponse(BaseModel):
    short_code: str
    short_url: str
    long_url: str
    is_custom_alias: bool
    created_at: datetime
    expires_at: datetime | None = None


class StatsResponse(BaseModel):
    short_code: str
    long_url: str
    click_count: int
    created_at: datetime
    expires_at: datetime | None = None
    last_clicked_at: datetime | None = None
