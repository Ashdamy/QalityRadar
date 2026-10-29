"""El modelo de calidad ISO/IEC 25010:2023 tal como lo usa QalitiRadar.

Una sola fuente para los nombres que se ensenan: antes habia una copia de la
tabla en el PDF, otra en el resumen y otra en la comparacion, y al cambiar la
norma cada una se quedaba atras por su lado.

Las claves internas (`usability`, `portability`...) son las de 2011 y NO se
renombran: estan guardadas como texto en cada analisis, en el enum de tipos
de hallazgo y en las comparaciones ya hechas. Renombrarlas obligaria a
migrar el historico entero para que el usuario viera exactamente lo mismo que
cambiando la etiqueta. Ver docs/ISO_25010_MAPPING.md.
"""

# Las caracteristicas de 2023 que cubrimos, 8 de las 9, en el orden de la
# norma. La clave es la interna; donde la norma renombro, la clave se queda y
# cambia la etiqueta.
#
# Proteccion (safety) queda fuera a proposito: exige una evaluacion humana del
# riesgo real del sistema y no se puede inferir leyendo codigo o HTML. Como no
# suma ni resta a la nota, no se ensena.
CARACTERISTICAS_2023: dict[str, str] = {
    "functional_suitability": "Adecuación funcional",
    "performance": "Eficiencia de desempeño",
    "compatibility": "Compatibilidad",
    # Antes "usabilidad".
    "usability": "Capacidad de interacción",
    "reliability": "Fiabilidad",
    "security": "Seguridad",
    "maintainability": "Mantenibilidad",
    # Antes "portabilidad".
    "portability": "Flexibilidad",
}

DIMENSION_LABELS: dict[str, str] = {
    **CARACTERISTICAS_2023,
    # En 2023 la accesibilidad deja de ser una subcaracteristica con ese
    # nombre y pasa a cubrirse con "inclusividad" dentro de la capacidad de
    # interaccion. Se mantiene como eje propio porque se mide con pruebas
    # distintas y tiene su propio peso en el modo URL.
    "accessibility": "Accesibilidad (inclusividad)",
    # No es ISO: ver scoring_service.
    "project_activity": "Actividad del proyecto",
}

# En el modo combinado las dimensiones llegan como "origen:nombre", porque
# codigo y produccion miden ambos "security" sin ser lo mismo.
ORIGIN_LABELS = {"codigo": "código", "produccion": "producción"}


def dimension_label(name: str) -> str:
    origen, separador, base = name.partition(":")
    if not separador:
        return DIMENSION_LABELS.get(name, name)
    etiqueta = DIMENSION_LABELS.get(base, base)
    return f"{etiqueta} ({ORIGIN_LABELS.get(origen, origen)})"
