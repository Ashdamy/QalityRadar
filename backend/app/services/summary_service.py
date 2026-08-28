"""Resumen ejecutivo de una comparacion entre analisis.

Decision de MVP acordada: Hugging Face Inference API (Mistral-7B-Instruct,
capa gratuita) con **plantilla de respaldo** si la API falla, tarda demasiado
o no hay clave configurada.

El respaldo no es un parche: es el camino normal cuando no hay clave, y
produce un resumen correcto y util con los mismos datos. Nunca se devuelve
un texto vacio ni un error al usuario por no poder llamar al modelo.

Al modelo se le envian solo cifras y titulos de hallazgos. Nunca sale codigo
del usuario hacia un tercero.
"""

import httpx

HF_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
HF_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
HF_TIMEOUT_SECONDS = 25

DIMENSION_LABELS = {
    "functional_suitability": "adecuacion funcional",
    "reliability": "fiabilidad",
    "security": "seguridad",
    "maintainability": "mantenibilidad",
    "portability": "portabilidad",
    "project_activity": "actividad del proyecto",
}


def build_summary(
    *,
    repository_name: str,
    previous_score: float,
    current_score: float,
    days_between: int | None,
    improvements: list[str],
    regressions: list[str],
    api_key: str | None = None,
) -> tuple[str, str]:
    """Devuelve (texto, origen), donde origen es 'modelo' o 'plantilla'."""
    if api_key:
        texto = _try_model(
            repository_name=repository_name,
            previous_score=previous_score,
            current_score=current_score,
            days_between=days_between,
            improvements=improvements,
            regressions=regressions,
            api_key=api_key,
        )
        if texto:
            return texto, "modelo"

    return (
        _from_template(
            previous_score=previous_score,
            current_score=current_score,
            days_between=days_between,
            improvements=improvements,
            regressions=regressions,
        ),
        "plantilla",
    )


def _from_template(
    *,
    previous_score: float,
    current_score: float,
    days_between: int | None,
    improvements: list[str],
    regressions: list[str],
) -> str:
    delta = round(current_score - previous_score, 1)
    periodo = f" en {days_between} dias" if days_between else ""

    if delta > 0:
        apertura = f"El proyecto ha mejorado {abs(delta):g} puntos{periodo}, de {previous_score:g} a {current_score:g}."
    elif delta < 0:
        apertura = f"El proyecto ha retrocedido {abs(delta):g} puntos{periodo}, de {previous_score:g} a {current_score:g}."
    else:
        apertura = f"La puntuacion se mantiene en {current_score:g}{periodo}."

    partes = [apertura]

    if improvements:
        principales = "; ".join(improvements[:3])
        partes.append(f"Lo que mejoro: {principales}.")
    if regressions:
        principales = "; ".join(regressions[:3])
        partes.append(f"Lo que empeoro: {principales}.")

    if regressions:
        partes.append(f"Prioridad para el proximo sprint: {regressions[0].rstrip('.')}.")
    elif improvements:
        partes.append("No hay regresiones: conviene sostener el ritmo actual.")
    else:
        partes.append("No se detectaron cambios relevantes entre ambos analisis.")

    return " ".join(partes)


def _try_model(
    *,
    repository_name: str,
    previous_score: float,
    current_score: float,
    days_between: int | None,
    improvements: list[str],
    regressions: list[str],
    api_key: str,
) -> str | None:
    prompt = _build_prompt(
        repository_name=repository_name,
        previous_score=previous_score,
        current_score=current_score,
        days_between=days_between,
        improvements=improvements,
        regressions=regressions,
    )
    try:
        respuesta = httpx.post(
            HF_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "inputs": prompt,
                "parameters": {"max_new_tokens": 320, "temperature": 0.3, "return_full_text": False},
            },
            timeout=HF_TIMEOUT_SECONDS,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except (httpx.HTTPError, ValueError):
        return None

    if isinstance(datos, list) and datos and isinstance(datos[0], dict):
        texto = (datos[0].get("generated_text") or "").strip()
        # Un resumen demasiado corto no aporta nada: mejor la plantilla.
        return texto if len(texto) > 80 else None
    return None


def _build_prompt(
    *,
    repository_name: str,
    previous_score: float,
    current_score: float,
    days_between: int | None,
    improvements: list[str],
    regressions: list[str],
) -> str:
    mejoras = "\n".join(f"- {m}" for m in improvements[:6]) or "- ninguna"
    regresiones = "\n".join(f"- {r}" for r in regressions[:6]) or "- ninguna"
    periodo = f"{days_between} dias" if days_between else "un periodo no determinado"

    return (
        "[INST] Eres un consultor tecnico. Redacta en espanol un resumen ejecutivo breve "
        "(maximo 5 frases) sobre la evolucion de la calidad de un proyecto de software.\n\n"
        f"Proyecto: {repository_name}\n"
        f"Puntuacion anterior: {previous_score:g}/100\n"
        f"Puntuacion actual: {current_score:g}/100\n"
        f"Periodo: {periodo}\n\n"
        f"Mejoras detectadas:\n{mejoras}\n\n"
        f"Regresiones detectadas:\n{regresiones}\n\n"
        "Incluye: una frase de apertura con el cambio neto, lo mas relevante que mejoro, "
        "lo que empeoro, y una unica recomendacion prioritaria para el proximo sprint. "
        "Tono profesional pero accesible. No inventes datos que no aparezcan arriba. [/INST]"
    )
