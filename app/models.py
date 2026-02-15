from __future__ import annotations

from pydantic import BaseModel


class TaskLine(BaseModel):
    task: str
    role: str
    hours_min: float
    hours_base: float
    hours_max: float


class Phase(BaseModel):
    name: str
    tasks: list[TaskLine]


class Timeline(BaseModel):
    total_weeks_min: int
    total_weeks_max: int
    note: str = ""


class Variant(BaseModel):
    name: str
    description: str = ""
    phases: list[Phase]
    timeline: Timeline | None = None


class EstimateResult(BaseModel):
    project_name: str
    client: str = ""
    project_type: str = ""
    scope_summary: str
    assumptions: list[str] = []
    risks: list[str] = []
    out_of_scope: list[str] = []
    variants: list[Variant]


class GptResponse(BaseModel):
    status: str  # "need_info" | "ready"
    questions: list[str] = []
    result: EstimateResult | None = None
