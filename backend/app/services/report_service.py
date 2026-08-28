"""Genera el informe de un analisis en PDF.

Se usa ReportLab porque es Python puro: no necesita GTK ni un navegador sin
interfaz, asi que funciona igual en Windows, Linux y en el contenedor de
produccion sin dependencias del sistema.

El PDF se construye a partir de los datos ya persistidos del analisis; no se
vuelve a analizar nada.
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

DIMENSION_LABELS = {
    "functional_suitability": "Adecuación funcional",
    "reliability": "Fiabilidad",
    "security": "Seguridad",
    "maintainability": "Mantenibilidad",
    "portability": "Portabilidad",
    "project_activity": "Actividad del proyecto",
}

SEVERITY_LABELS = {
    "critical": "Crítico",
    "high": "Alto",
    "medium": "Medio",
    "low": "Bajo",
    "info": "Info",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# El informe va sobre fondo blanco: se imprime y se comparte, no se lee en la
# aplicacion. Los colores son los del producto adaptados a papel.
INK = colors.HexColor("#1a1d24")
MUTED = colors.HexColor("#5a616e")
FAINT = colors.HexColor("#8b919c")
RULE = colors.HexColor("#d6d9de")
ACCENT = colors.HexColor("#0d7d8f")
GOOD = colors.HexColor("#1e7a45")
WARN = colors.HexColor("#9a6b0f")
BAD = colors.HexColor("#b02a1c")


def _score_color(score: float) -> colors.Color:
    if score >= 80:
        return GOOD
    if score >= 50:
        return WARN
    return BAD


def _severity_color(severity: str) -> colors.Color:
    if severity in ("critical", "high"):
        return BAD
    if severity == "medium":
        return WARN
    return FAINT


def build_analysis_report(
    *,
    repository_full_name: str,
    analysis,
    dimensions: list,
    findings: list,
) -> bytes:
    """Devuelve el PDF del análisis como bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"QalitiRadar - {repository_full_name}",
        author="QalitiRadar",
    )

    base = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        "titulo", parent=base["Title"], fontSize=19, leading=23, textColor=INK, alignment=TA_LEFT
    )
    estilo_sub = ParagraphStyle("sub", parent=base["Normal"], fontSize=9.5, textColor=MUTED, leading=13)
    estilo_h2 = ParagraphStyle(
        "h2", parent=base["Heading2"], fontSize=12.5, textColor=INK, spaceBefore=14, spaceAfter=6
    )
    estilo_cuerpo = ParagraphStyle("cuerpo", parent=base["Normal"], fontSize=9.5, leading=13.5, textColor=INK)
    estilo_nota = ParagraphStyle("nota", parent=base["Normal"], fontSize=8, leading=11, textColor=FAINT)
    estilo_mono = ParagraphStyle(
        "mono", parent=base["Normal"], fontName="Courier", fontSize=8, textColor=FAINT
    )

    story = []

    story.append(Paragraph("Informe de calidad de software", estilo_titulo))
    story.append(Spacer(1, 3))
    story.append(Paragraph(repository_full_name, estilo_sub))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", color=RULE, thickness=0.8))
    story.append(Spacer(1, 12))

    score = float(analysis.overall_score or 0)
    confianza = float(analysis.confidence_level or 0)
    generado = datetime.now().strftime("%d/%m/%Y %H:%M")

    resumen = Table(
        [
            [
                Paragraph("<b>PUNTUACIÓN GENERAL</b>", estilo_nota),
                Paragraph("<b>CONFIANZA</b>", estilo_nota),
                Paragraph("<b>ANALIZADO</b>", estilo_nota),
            ],
            [
                Paragraph(
                    f'<font size="27" color="#{_score_color(score).hexval()[2:]}">'
                    f'<b>{score:.0f}</b></font><font size="11" color="#8b919c">/100</font>',
                    estilo_cuerpo,
                ),
                Paragraph(f'<font size="15">{confianza:.0f}%</font>', estilo_cuerpo),
                Paragraph(
                    analysis.completed_at.strftime("%d/%m/%Y") if analysis.completed_at else "—",
                    estilo_cuerpo,
                ),
            ],
        ],
        colWidths=[60 * mm, 45 * mm, 55 * mm],
    )
    resumen.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("TOPPADDING", (0, 1), (-1, 1), 0),
            ]
        )
    )
    story.append(resumen)

    if analysis.commit_hash:
        story.append(Spacer(1, 8))
        mensaje = (analysis.commit_message or "").strip()
        story.append(
            Paragraph(
                f"commit {analysis.commit_hash[:10]} · rama {analysis.branch or '—'}"
                + (f" · {mensaje[:90]}" if mensaje else ""),
                estilo_mono,
            )
        )

    # -- Dimensiones ---------------------------------------------------------
    story.append(Paragraph("Dimensiones ISO/IEC 25010", estilo_h2))

    filas = [["Dimensión", "Puntuación", "Peso"]]
    estilos_fila = []
    for i, d in enumerate(sorted(dimensions, key=lambda x: -float(x.score)), start=1):
        valor = float(d.score)
        filas.append(
            [
                DIMENSION_LABELS.get(d.name, d.name),
                f"{valor:.0f}/100",
                f"{float(d.weight) * 100:.0f}%",
            ]
        )
        estilos_fila.append(("TEXTCOLOR", (1, i), (1, i), _score_color(valor)))

    tabla = Table(filas, colWidths=[95 * mm, 35 * mm, 30 * mm])
    tabla.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE),
                ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                *estilos_fila,
            ]
        )
    )
    story.append(tabla)

    # -- Hallazgos -----------------------------------------------------------
    story.append(Paragraph(f"Hallazgos ({len(findings)})", estilo_h2))

    if not findings:
        story.append(
            Paragraph(
                "No se encontró ningún problema en las dimensiones analizadas.", estilo_cuerpo
            )
        )
    else:
        ordenados = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
        for finding in ordenados:
            color = _severity_color(finding.severity)
            etiqueta = SEVERITY_LABELS.get(finding.severity, finding.severity)
            bloque = [
                Paragraph(
                    f'<font color="#{color.hexval()[2:]}"><b>[{etiqueta}]</b></font> '
                    f"<b>{_escape(finding.title)}</b>",
                    estilo_cuerpo,
                ),
                Spacer(1, 2),
                Paragraph(_escape(finding.description), estilo_cuerpo),
            ]
            if finding.file_path:
                bloque += [Spacer(1, 2), Paragraph(_escape(finding.file_path), estilo_mono)]
            if finding.recommendation:
                bloque += [
                    Spacer(1, 2),
                    Paragraph(
                        f'<font color="#5a616e"><b>Recomendación:</b></font> '
                        f"{_escape(finding.recommendation)}",
                        estilo_cuerpo,
                    ),
                ]
            bloque.append(Spacer(1, 10))
            # Un hallazgo no debe partirse entre dos paginas.
            story.append(KeepTogether(bloque))

    # -- Aviso legal ---------------------------------------------------------
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", color=RULE, thickness=0.8))
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            f"Generado por QalitiRadar el {generado}. Esta puntuación es una "
            f"<b>aproximación</b> basada en el modelo de calidad ISO/IEC 25010 y cubre "
            f"{len(dimensions)} de sus dimensiones. <b>No constituye una certificación "
            f"oficial</b> ni sustituye una evaluación formal. Los resultados pueden "
            f"contener falsos positivos y falsos negativos.",
            estilo_nota,
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _escape(text: str | None) -> str:
    """ReportLab interpreta un subconjunto de HTML en los parrafos."""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
