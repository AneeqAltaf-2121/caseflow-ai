import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuthorizeUrlRead(BaseModel):
    authorize_url: str
    state: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    avatar_url: str | None
    created_at: datetime
