from pydantic import BaseModel


class FindingOut(BaseModel):
    type: str
    severity: str
    title: str
    description: str
    file_path: str | None = None
    recommendation: str | None = None


class DimensionOut(BaseModel):
    name: str
    score: float
    weight: float


class AnalysisOut(BaseModel):
    id: str
    status: str
    overall_score: float | None = None
    confidence_level: float | None = None
    commit_hash: str | None = None
    commit_message: str | None = None
    error_message: str | None = None
    dimensions: list[DimensionOut] = []
    findings: list[FindingOut] = []
