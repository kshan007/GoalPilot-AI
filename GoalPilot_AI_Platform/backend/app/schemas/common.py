"""Shared API schema helpers."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class OkResponse(BaseModel):
    ok: bool = True
    message: str = ""


class MessageResponse(BaseModel):
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class Paginated(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[Any]
