"""Veredicto de conformidad: apto, apto condicionado o no apto.

Una sola palabra para quien no va a leer once dimensiones: se puede usar o no,
y con que reservas. Se calcula al leer el analisis a partir de lo que ya esta
guardado (nota, hallazgos y confianza), asi que no necesita migracion y vale
tambien para los analisis antiguos.

Reglas, gana el caso mas severo:

- No apto: nota menor de 40, o algun hallazgo critico.
- Apto condicionado: nota entre 40 y 59, o algun hallazgo alto.
- Apto: nota de 60 o mas y ningun hallazgo alto ni critico.

Es provisional si la confianza es menor del 50 % o si la calidad del codigo
solo se pudo analizar en parte (cobertura parcial de lenguajes): el nivel no
cambia, pero se avisa de que descansa sobre poca evidencia.

Los umbrales coinciden con los techos por gravedad de scoring_service (un
critico limita la nota a 40 y un alto a 70), asi que el veredicto nunca
contradice a la nota.
"""

from collections import Counter

APTO = "apto"
APTO_CONDICIONADO = "apto_condicionado"
NO_APTO = "no_apto"

NOTA_APTO = 60.0
NOTA_CONDICIONADO = 40.0
CONFIANZA_MINIMA = 50.0

TITULO_COBERTURA_PARCIAL = "Cobertura parcial de lenguajes"

TEXTO_FIJO = "Indicador interno basado en ISO/IEC 25010. No constituye una certificación oficial."

ETIQUETAS = {APTO: "Apto", APTO_CONDICIONADO: "Apto condicionado", NO_APTO: "No apto"}

# Area en la que cae cada tipo de hallazgo, para que el motivo diga donde mirar.
_AREA = {
    "security": "Seguridad",
    "dependency": "Seguridad",
    "test_coverage": "Fiabilidad",
    "documentation": "Adecuación funcional",
    "cicd": "Flexibilidad",
    "structure": "Mantenibilidad",
    "activity": "Actividad del proyecto",
    "performance": "Eficiencia de desempeño",
    "accessibility": "Accesibilidad",
    "usability": "Capacidad de interacción",
    "seo": "Capacidad de interacción",
    "compatibility": "Compatibilidad",
}

_GRAVEDAD = {"critical": ("crítico", "críticos"), "high": ("alto", "altos")}


def _nota_legible(nota: float) -> str:
    return f"{nota:.0f}" if float(nota).is_integer() else f"{nota:.1f}".replace(".", ",")


def _motivos_por_hallazgos(hallazgos, severidad: str) -> list[str]:
    singular, plural = _GRAVEDAD[severidad]
    por_area = Counter(_AREA.get(h.type, "otras áreas") for h in hallazgos if h.severity == severidad)
    return [
        f"Hay {n} {'hallazgo' if n == 1 else 'hallazgos'} {singular if n == 1 else plural} en {area}"
        for area, n in por_area.most_common()
    ]


def calcular_veredicto(nota: float | None, hallazgos, confianza: float | None) -> dict | None:
    """Devuelve {nivel, etiqueta, provisional, motivos}, o None si no hay nota.

    `hallazgos` son objetos con `severity`, `type` y `title` (filas de la
    tabla `findings` o FindingData).
    """
    if nota is None:
        return None
    nota = float(nota)
    criticos = _motivos_por_hallazgos(hallazgos, "critical")
    altos = _motivos_por_hallazgos(hallazgos, "high")

    if nota < NOTA_CONDICIONADO or criticos:
        nivel = NO_APTO
    elif nota < NOTA_APTO or altos:
        nivel = APTO_CONDICIONADO
    else:
        nivel = APTO

    legible = _nota_legible(nota)
    if nota >= NOTA_APTO:
        motivo_nota = f"La nota global es {legible}, igual o superior a 60"
        if not criticos and not altos:
            motivo_nota += ", y no hay hallazgos altos ni críticos"
    elif nota >= NOTA_CONDICIONADO:
        motivo_nota = f"La nota global es {legible}, entre 40 y 59"
    else:
        motivo_nota = f"La nota global es {legible}, por debajo de 40"
    motivos = [motivo_nota, *criticos, *altos]

    provisional = False
    if confianza is None or float(confianza) < CONFIANZA_MINIMA:
        provisional = True
        motivos.append(
            "No se conoce la confianza del análisis"
            if confianza is None
            else f"La confianza del análisis es del {_nota_legible(float(confianza))} %, por debajo del 50 %"
        )
    if any(getattr(h, "title", None) == TITULO_COBERTURA_PARCIAL for h in hallazgos):
        provisional = True
        motivos.append("Cobertura parcial de lenguajes: parte del código no se pudo analizar")

    return {"nivel": nivel, "etiqueta": ETIQUETAS[nivel], "provisional": provisional, "motivos": motivos}
