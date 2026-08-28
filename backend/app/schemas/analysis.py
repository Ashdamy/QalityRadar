from pydantic import BaseModel


class FindingOut(BaseModel):
    type: str
    severity: str
    title: str
    description: str
    file_path: str | None = None
    # Los hallazgos de URL se ubican por direccion, no por archivo.
    url: str | None = None
    recommendation: str | None = None


class DimensionOut(BaseModel):
    name: str
    score: float
    weight: float


class CorrespondenceOut(BaseModel):
    """Aviso de que el repositorio y la URL podrian no ser el mismo proyecto."""

    kind: str  # "ok", "no_deployment" o "possible_mismatch"
    looks_related: bool
    confidence: str
    reasons: list[str] = []
    warning: str | None = None


class PlanItemOut(BaseModel):
    severity: str
    origin: str  # "codigo", "produccion" o "discrepancia"
    title: str
    detail: str | None = None


class CombinedOut(BaseModel):
    """Datos que solo existen en el modo combinado (codigo frente a produccion)."""

    repository_score: float | None = None
    url_score: float | None = None
    delta: float | None = None
    explanation: str | None = None
    recommendations: str | None = None
    improvement_plan: list[PlanItemOut] = []
    correspondence: CorrespondenceOut | None = None


class AnalysisOut(BaseModel):
    id: str
    status: str
    overall_score: float | None = None
    confidence_level: float | None = None
    commit_hash: str | None = None
    commit_message: str | None = None
    error_message: str | None = None
    summary_text: str | None = None
    summary_source: str | None = None
    analysis_type: str = "repository"
    dimensions: list[DimensionOut] = []
    findings: list[FindingOut] = []
    # Solo se rellena cuando analysis_type == "combined".
    combined: CombinedOut | None = None


class TimelineEntry(BaseModel):
    id: str
    status: str
    overall_score: float | None = None
    commit_hash: str | None = None
    commit_message: str | None = None
    created_at: str
    delta: float | None = None


class ProgressOut(BaseModel):
    total_analyses: int
    current_score: float | None = None
    best_score: float | None = None
    best_score_at: str | None = None
    first_score: float | None = None
    total_delta: float | None = None
    days_tracked: int | None = None


class ChangeOut(BaseModel):
    dimension: str
    previous_score: float | None = None
    current_score: float | None = None
    delta: float
    description: str
    severity: str | None = None


class ComparisonOut(BaseModel):
    id: str
    analysis_1_id: str
    analysis_2_id: str
    previous_score: float | None = None
    current_score: float | None = None
    score_delta: float
    trend: str
    summary_text: str | None = None
    summary_source: str | None = None
    improvements: list[ChangeOut] = []
    regressions: list[ChangeOut] = []
