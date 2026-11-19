"""Персональные данные кандидата, которые импорт отделяет от текста резюме."""
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PiiData(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    age: int | None = Field(default=None, ge=14, le=100)
    phone: str | None = None
    email: str | None = None
    city: str | None = None
    citizenship: str | None = None
    links: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
