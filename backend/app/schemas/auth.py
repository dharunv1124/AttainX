"""
Authentication Pydantic schemas.
"""

from typing import Optional
from pydantic import BaseModel, Field
from app.db.models import UserRole


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    full_name: str
    role: UserRole


class TokenPayload(BaseModel):
    sub: str  # username
    role: UserRole
    exp: Optional[int] = None
