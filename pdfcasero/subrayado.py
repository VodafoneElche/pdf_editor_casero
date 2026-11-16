"""Subrayador fosforescente: marcas de color sobre el texto, como un rotulador.

Se guardan como anotaciones de resaltado (Highlight) de verdad, así se ven
igual en Acrobat, Chrome, Edge o el móvil, y se pueden quitar después.
"""

from __future__ import annotations

import pymupdf

# Colores de rotulador fluorescente. El PDF los mezcla en modo "multiplicar",
# así que el texto negro de debajo se sigue leyendo bien.
COLORES = (
    ("amarillo", "Amarillo", (1.0, 0.95, 0.0)),
    ("verde", "Verde", (0.35, 1.0, 0.2)),
    ("rosa", "Rosa", (1.0, 0.35, 0.8)),
    ("rojo", "Rojo", (1.0, 0.2, 0.2)),
)
COLOR = {clave: rgb for clave, _, rgb in COLORES}


def _juntar_por_lineas(rects) -> list[pymupdf.Rect]:
    """Une los recuadros de las palabras de una misma línea en una sola franja."""
    lineas: list[pymupdf.Rect] = []
    for r in sorted((pymupdf.Rect(r) for r in rects), key=lambda r: (r.y0, r.x0)):
        if r.is_empty:
            continue
        ultima = lineas[-1] if lineas else None
        if ultima is not None:
            solape = min(ultima.y1, r.y1) - max(ultima.y0, r.y0)
            if solape > 0.5 * min(ultima.height, r.height):
                # Rect | Rect da un recuadro nuevo: hay que guardarlo en la lista
                lineas[-1] = ultima | r
                continue
        lineas.append(r)
    return lineas


def subrayar(pagina: pymupdf.Page, rects, rgb) -> int | None:
    """Pinta con el rotulador los recuadros dados (en puntos PDF). Devuelve el xref."""
    lineas = _juntar_por_lineas(rects)
    if not lineas:
        return None
    # Mismas coordenadas que las palabras de get_text, que son las que elige el visor
    annot = pagina.add_highlight_annot(quads=[r.quad for r in lineas])
    annot.set_colors(stroke=rgb)
    annot.set_info(title="PDF Familiar")
    annot.update()
    return annot.xref


def subrayados(pagina: pymupdf.Page) -> list[tuple[int, list[pymupdf.Rect]]]:
    """Resaltados de la página (los nuestros y los de otros programas)."""
    resultado = []
    for annot in pagina.annots(types=[pymupdf.PDF_ANNOT_HIGHLIGHT]):
        verts = annot.vertices or []
        rects = [pymupdf.Quad(verts[i : i + 4]).rect for i in range(0, len(verts) - 3, 4)]
        resultado.append((annot.xref, rects or [annot.rect]))
    return resultado


def subrayado_en(pagina: pymupdf.Page, x: float, y: float) -> int | None:
    """El resaltado bajo el punto (el de encima si hay varios)."""
    p = pymupdf.Point(x, y)
    for xref, rects in reversed(subrayados(pagina)):
        if any(r.contains(p) for r in rects):
            return xref
    return None


def quitar(pagina: pymupdf.Page, xref: int) -> None:
    for annot in pagina.annots(types=[pymupdf.PDF_ANNOT_HIGHLIGHT]):
        if annot.xref == xref:
            pagina.delete_annot(annot)
            return
