"""Resumen ejecutivo de una comparacion entre analisis.

Decision de MVP acordada: Hugging Face con **plantilla de respaldo** si la API
falla, tarda demasiado o no hay clave configurada.

El respaldo no es un parche: es el camino normal cuando no hay clave, y
produce un resumen correcto y util con los mismos datos. Nunca se devuelve un
texto vacio ni un error al usuario por no poder llamar al modelo.

Nota sobre el endpoint: Hugging Face retiro `api-inference.huggingface.co`
(el dominio ya ni siquiera resuelve) y lo sustituyo por un router compatible
con la API de OpenAI. Ademas, no todos los modelos estan disponibles ahi;
Mistral-7B-Instruct, que estaba en el plan original, ya no lo esta.

Al modelo se le envian solo cifras y titulos de hallazgos. Nunca sale codigo
del usuario hacia un tercero.
"""

import httpx

HF_URL = "https://router.huggingface.co/v1/chat/completions"
HF_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
HF_TIMEOUT_SECONDS = 45

# Por debajo de esto el modelo no ha dicho nada util y sale mejor la plantilla.
MIN_USEFUL_SUMMARY_CHARS = 80


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
        partes.append("Lo que mejoro: " + "; ".join(_sin_punto(m) for m in improvements[:3]) + ".")
    if regressions:
        partes.append("Lo que empeoro: " + "; ".join(_sin_punto(r) for r in regressions[:3]) + ".")

    if regressions:
        partes.append(f"Prioridad para el proximo sprint: corregir {_sin_punto(regressions[0]).lower()}.")
    elif improvements:
        partes.append("No hay regresiones: conviene sostener el ritmo actual.")
    else:
        partes.append("No se detectaron cambios relevantes entre ambos analisis.")

    return " ".join(partes)


def _sin_punto(texto: str) -> str:
    return texto.strip().rstrip(".")


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
    mejoras = "\n".join(f"- {m}" for m in improvements[:6]) or "- ninguna"
    regresiones = "\n".join(f"- {r}" for r in regressions[:6]) or "- ninguna"
    periodo = f"{days_between} dias" if days_between else "un periodo no determinado"

    prompt = (
        f"Proyecto: {repository_name}\n"
        f"Puntuacion anterior: {previous_score:g}/100\n"
        f"Puntuacion actual: {current_score:g}/100\n"
        f"Periodo entre analisis: {periodo}\n\n"
        f"Mejoras detectadas:\n{mejoras}\n\n"
        f"Regresiones detectadas:\n{regresiones}\n\n"
        "Redacta el resumen ejecutivo."
    )

    try:
        respuesta = httpx.post(
            HF_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": HF_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Eres un consultor tecnico. Escribes en espanol un resumen ejecutivo "
                            "de maximo cinco frases sobre la evolucion de la calidad de un "
                            "proyecto de software. Incluyes: el cambio neto, lo mas relevante que "
                            "mejoro, lo que empeoro, y una unica recomendacion prioritaria para el "
                            "proximo sprint. Tono profesional pero accesible. No inventas ningun "
                            "dato que no aparezca en la informacion facilitada. Respondes solo con "
                            "el resumen, sin encabezados ni vinetas."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 320,
                "temperature": 0.3,
            },
            timeout=HF_TIMEOUT_SECONDS,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
        texto = (datos["choices"][0]["message"]["content"] or "").strip()
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        # Cualquier fallo cae a la plantilla: mejor un resumen correcto hecho
        # con los mismos datos que un error en la cara del usuario.
        return None

    return texto if len(texto) >= MIN_USEFUL_SUMMARY_CHARS else None
