"""Leer el texto de un PDF de ReportLab en las pruebas, sin dependencias.

ReportLab guarda cada pagina en un flujo ASCII85 sobre Flate; se deshacen las
dos capas con la libreria estandar. Las letras con tilde quedan como escapes
octales de PDF (por ejemplo, \\363 para la o con tilde): las pruebas buscan
fragmentos sin tilde.
"""

import base64
import re
import zlib


def paginas_del_pdf(pdf: bytes) -> list[str]:
    """Texto de cada flujo de contenido, en orden (uno por pagina)."""
    return [
        zlib.decompress(base64.a85decode(b"<~" + flujo.strip(), adobe=True)).decode("latin-1")
        for flujo in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S)
        if flujo.strip().endswith(b"~>")
    ]


def texto_del_pdf(pdf: bytes) -> str:
    return "".join(paginas_del_pdf(pdf))
