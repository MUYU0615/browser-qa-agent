from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RunStatus = Literal["queued", "running", "completed", "failed"]


class CreateRunRequest(BaseModel):
    url: str = Field(min_length=4)


class RunSummary(BaseModel):
    id: str
    url: str
    status: RunStatus
    current_node: str
    created_at: str
    updated_at: str


class RunResponse(BaseModel):
    id: str
    url: str
    status: RunStatus
    current_node: str
    created_at: str
    updated_at: str
    events: list[dict] = Field(default_factory=list)
    llm_calls: list[dict] = Field(default_factory=list)
    attempts: list[dict] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)
    issues: list[dict] = Field(default_factory=list)
    report_path: str | None = None
    error: str | None = None
