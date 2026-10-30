from pydantic import BaseModel, Field


class FindingOut(BaseModel):
    type: str
    severity: str
    title: str
    description: str
    file_path: str | None = None
    # Los hallazgos de URL se ubican por direccion, no por archivo.
    url: str | None = None
    recommendation: str | None = None


class SubcaracteristicaOut(BaseModel):
    name: str
    # Ambos nulos cuando no se mide: "sin medir", nunca 0.
    earned: float | None = None
    max: float | None = None
    measured: bool
    # False en los grupos que suman puntos pero no son de la norma.
    iso: bool
    # De donde sale el dato: sonarcloud | qalitiradar | estimado | sin_medir
    # en mantenibilidad; lighthouse | axe-core | qalitiradar donde puede venir
    # del navegador real. Nulo en el resto y en analisis antiguos.
    origin: str | None = None


class SonarImportIn(BaseModel):
    project_key: str = Field(min_length=1, max_length=400)


class SonarOut(BaseModel):
    project_key: str
    imported_at: str
    metrics: dict[str, float]


class ViolacionAxeOut(BaseModel):
    id: str
    impact: str  # critical | serious | moderate | minor
    nodes: int
    help: str


class NavegadorOut(BaseModel):
    """Medicion en navegador real, que llega despues del analisis estatico."""

    status: str  # pending | ok | failed
    reason: str | None = None
    measured_at: str | None = None
    lcp_ms: float | None = None
    tbt_ms: float | None = None
    cls: float | None = None
    # bueno | mejorable | malo, por metrica.
    ratings: dict[str, str] = {}
    axe_violations: list[ViolacionAxeOut] = []
    axe_passes: int | None = None


class BenchmarkItemOut(BaseModel):
    dimension: str
    label: str
    score: float
    reference: float
    delta: float


class BenchmarkOut(BaseModel):
    language: str
    # Mientras sea True, el frontend tiene que decir que NO son datos reales.
    is_simulated: bool
    source: str
    items: list[BenchmarkItemOut]


class VeredictoOut(BaseModel):
    nivel: str  # apto | apto_condicionado | no_apto
    etiqueta: str
    provisional: bool
    motivos: list[str]
    aviso: str


class DimensionOut(BaseModel):
    name: str
    score: float
    weight: float
    # Nulo en los analisis anteriores al desglose.
    subcharacteristics: list[SubcaracteristicaOut] | None = None


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
    # Ausente en los analisis de URL, que no parten de un repositorio.
    repository_full_name: str | None = None
    dimensions: list[DimensionOut] = []
    findings: list[FindingOut] = []
    # Solo se rellena cuando analysis_type == "combined".
    combined: CombinedOut | None = None
    # Si la calidad del codigo solo pudo analizarse en parte del proyecto.
    coverage_notice: str | None = None
    # Calculado al leer; nulo si el analisis no ha terminado bien.
    verdict: VeredictoOut | None = None
    # Metricas importadas de SonarCloud, si las hay.
    sonar: SonarOut | None = None
    # Solo en analisis de URL con la medicion en navegador activada.
    browser: NavegadorOut | None = None


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


class ShareLinkOut(BaseModel):
    token: str
    expires_at: str


class AnalysisListItem(BaseModel):
    """Una linea del listado de "mis analisis"."""

    id: str
    analysis_type: str
    status: str
    # Nombre del repositorio o direccion analizada, lo que corresponda: sin
    # esto el listado seria una lista de identificadores sin significado.
    target: str
    overall_score: float | None = None
    created_at: str
