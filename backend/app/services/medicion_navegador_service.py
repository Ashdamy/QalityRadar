"""Anexa la medicion en navegador real a un analisis de URL ya entregado.

Va en dos tiempos: el analisis estatico se entrega en cuanto termina, con
`raw_data["browser"] = {"status": "pending"}`, y esta tarea llega despues.
Si la medicion sale bien, se repuntuan eficiencia de desempeno y
accesibilidad, se anaden los hallazgos de axe y se recalcula la nota. Si
falla, se deja el motivo y todo lo demas queda como estaba: la medicion
nunca rompe un analisis.

No hace falta migracion: la medicion se guarda en `analyses.raw_data`, que
ya es donde viven las metricas medidas de un analisis de URL.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm.attributes import flag_modified

from app.analyzers.base import FindingData
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.analysis import Analysis, Dimension, Finding
from app.models.deployed_app import DeployedApp
from app.services.scoring_service import calculate_url_overall_score, score_url_dimension, subcharacteristics
from app.utils.navegador import Contenedor, MedicionFallida, calificar, medir
from app.utils.url_validation import UnsafeUrlError

PENDIENTE = "pending"
HECHA = "ok"
FALLIDA = "failed"

# Una violacion critica es grave, pero no tanto como un secreto expuesto: con
# "critical" una sola regla de axe bajaria la nota a 40 y dejaria el
# veredicto en "No apto". Las moderadas y menores solo informan.
SEVERIDAD_AXE = {"critical": "high", "serious": "medium", "moderate": "info", "minor": "info"}
ETIQUETA_IMPACTO = {"critical": "crítica", "serious": "seria", "moderate": "moderada", "minor": "menor"}
# Para encontrar y sustituir los hallazgos de una medicion anterior.
PREFIJO_HALLAZGO = "Accesibilidad (axe-core): "


def hallazgos_de_axe(violaciones: list[dict], url: str | None) -> list[FindingData]:
    return [
        FindingData(
            type="accessibility",
            severity=SEVERIDAD_AXE[v["impact"]],
            title=f"{PREFIJO_HALLAZGO}{v['help'] or v['id']}"[:200],
            description=(
                f"Violación {ETIQUETA_IMPACTO[v['impact']]} de la regla «{v['id']}» en "
                f"{v['nodes']} {'elemento' if v['nodes'] == 1 else 'elementos'} de la página, "
                "comprobada en un navegador real."
            ),
            url=url,
            recommendation=f"Revisa la regla {v['id']} en la documentación de axe-core (dequeuniversity.com/rules/axe).",
        )
        for v in violaciones
    ]


def marcar_pendiente(analysis: Analysis) -> None:
    analysis.raw_data = {**(analysis.raw_data or {}), "browser": {"status": PENDIENTE}}
    flag_modified(analysis, "raw_data")


def _guardar(db, analysis: Analysis, datos: dict) -> None:
    analysis.raw_data = {**(analysis.raw_data or {}), "browser": datos}
    flag_modified(analysis, "raw_data")
    db.commit()


def medir_y_anexar(analysis_id: str, medir_fn=medir) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        analysis = db.get(Analysis, uuid.UUID(analysis_id))
        if analysis is None or analysis.status != "completed":
            return
        app_row = db.get(DeployedApp, analysis.app_id) if analysis.app_id else None
        if app_row is None:
            return

        try:
            medicion = medir_fn(app_row.url, Contenedor(settings.navegador_imagen, settings.navegador_red))
        except (MedicionFallida, UnsafeUrlError) as exc:
            _guardar(db, analysis, {"status": FALLIDA, "reason": str(exc)[:200]})
            return
        except Exception:  # noqa: BLE001
            _guardar(db, analysis, {"status": FALLIDA, "reason": "No se pudo medir en el navegador aislado."})
            return

        _aplicar(db, analysis, app_row.url, medicion)
    finally:
        db.close()


def _aplicar(db, analysis: Analysis, url: str, medicion: dict) -> None:
    datos = {
        "status": HECHA,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        **medicion,
        "ratings": {k: calificar(k, medicion[k]) for k in ("lcp_ms", "tbt_ms", "cls") if k in medicion},
    }

    dimensiones = {d.name: d for d in db.scalars(select(Dimension).where(Dimension.analysis_id == analysis.id))}
    for nombre in ("performance", "accessibility"):
        dim = dimensiones.get(nombre)
        if dim is None:
            continue
        entrada = {**(dim.raw_metrics or {}), "browser": medicion}
        dim.score = score_url_dimension(nombre, entrada)
        dim.subcharacteristics = subcharacteristics(nombre, entrada, url=True)

    # Una medicion repetida sustituye a la anterior, no se le suma.
    db.execute(delete(Finding).where(Finding.analysis_id == analysis.id, Finding.title.startswith(PREFIJO_HALLAZGO)))
    for f in hallazgos_de_axe(medicion.get("axe", {}).get("violations", []), url):
        db.add(Finding(id=uuid.uuid4(), analysis_id=analysis.id, type=f.type, severity=f.severity,
                       title=f.title, description=f.description, url=f.url, recommendation=f.recommendation))
    db.flush()

    hallazgos = db.scalars(select(Finding).where(Finding.analysis_id == analysis.id)).all()
    analysis.overall_score = calculate_url_overall_score({n: float(d.score) for n, d in dimensiones.items()}, list(hallazgos))
    _guardar(db, analysis, datos)
