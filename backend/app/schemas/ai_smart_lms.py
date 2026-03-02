from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BlueprintSection(BaseModel):
    title: str
    payload: dict[str, Any] | list[Any] | str


class SmartLMSBlueprintResponse(BaseModel):
    system_name: str = "AI Smart LMS"
    sections: list[BlueprintSection]


class DashboardGateResponse(BaseModel):
    has_active_course: bool
    message: str


class TutorGuardrailRequest(BaseModel):
    question: str = Field(min_length=3)
    current_topic: str = Field(min_length=2)


class TutorGuardrailResponse(BaseModel):
    accepted: bool
    reason: str
