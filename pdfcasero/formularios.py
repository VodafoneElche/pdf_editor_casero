"""Formularios: crear campos rellenables y rellenarlos.

Son campos de formulario PDF estándar (AcroForm), así que quien reciba el PDF
puede rellenarlos con Adobe Reader, Edge, Chrome o el móvil.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

TIPOS = {
    "texto": "Campo de texto",
    "multilinea": "Texto largo",
    "casilla": "Casilla",
}
TAM_CASILLA = 14
BORDE = (0.45, 0.5, 0.65)
FONDO = (0.93, 0.95, 1.0)


@dataclass
class Campo:
    xref: int
    tipo: str  # "texto", "multilinea", "casilla" u "otro" (campos de otros programas)
    nombre: str
    rect: pymupdf.Rect
    valor: str | bool

    @property
    def marcado(self) -> bool:
        return self.tipo == "casilla" and bool(self.valor)


def _tipo(w: pymupdf.Widget) -> str:
    if w.field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
        return "casilla"
    if w.field_type == pymupdf.PDF_WIDGET_TYPE_TEXT:
        return "multilinea" if w.field_flags & pymupdf.PDF_TX_FIELD_IS_MULTILINE else "texto"
    return "otro"


def _campo(w: pymupdf.Widget) -> Campo:
    tipo = _tipo(w)
    valor = w.field_value
    if tipo == "casilla":
        valor = valor not in (False, None, "", "Off")
    return Campo(w.xref, tipo, w.field_name or "", pymupdf.Rect(w.rect), valor if valor is not None else "")


def campos(pagina: pymupdf.Page) -> list[Campo]:
    return [_campo(w) for w in pagina.widgets()]


def campo_en(pagina: pymupdf.Page, x: float, y: float, margen: float = 2) -> Campo | None:
    for c in reversed(campos(pagina)):
        r = c.rect
        if r.x0 - margen <= x <= r.x1 + margen and r.y0 - margen <= y <= r.y1 + margen:
            return c
    return None


def _widget(pagina: pymupdf.Page, xref: int) -> pymupdf.Widget:
    for w in pagina.widgets():
        if w.xref == xref:
            return w
    raise KeyError(f"No existe el campo {xref}")


def nombre_libre(doc: pymupdf.Document, tipo: str) -> str:
    """Nombre que no esté usado en ningún campo del documento, p. ej. 'Texto 3'."""
    base = {"texto": "Texto", "multilinea": "Texto largo", "casilla": "Casilla"}.get(tipo, "Campo")
    usados = {w.field_name for pagina in doc for w in pagina.widgets()}
    i = 1
    while f"{base} {i}" in usados:
        i += 1
    return f"{base} {i}"


def crear(pagina: pymupdf.Page, tipo: str, rect: pymupdf.Rect, nombre: str) -> int:
    w = pymupdf.Widget()
    if tipo == "casilla":
        w.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
        x, y = rect.x0, rect.y0
        rect = pymupdf.Rect(x, y, x + TAM_CASILLA, y + TAM_CASILLA)
        w.field_value = False
    else:
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        rect = pymupdf.Rect(rect).normalize()
        if tipo == "multilinea":
            w.field_flags = pymupdf.PDF_TX_FIELD_IS_MULTILINE
            rect.y1 = max(rect.y1, rect.y0 + 36)
            w.text_fontsize = 10
        else:
            rect.y1 = max(rect.y1, rect.y0 + 18)
            w.text_fontsize = 11
        rect.x1 = max(rect.x1, rect.x0 + 40)
        w.field_value = ""
        w.text_font = "Helv"
    w.rect = rect
    w.field_name = nombre
    w.border_color = BORDE
    w.fill_color = FONDO
    w.border_width = 1
    return pagina.add_widget(w).xref


def mover(pagina: pymupdf.Page, xref: int, rect: pymupdf.Rect) -> None:
    w = _widget(pagina, xref)
    w.rect = pymupdf.Rect(rect).normalize()
    w.update()


def renombrar(pagina: pymupdf.Page, xref: int, nombre: str) -> None:
    # El nombre (/T) puede estar en el propio campo o en su "padre"; PyMuPDF no lo cambia solo
    doc = pagina.parent
    destino = xref
    tipo, valor = doc.xref_get_key(xref, "Parent")
    if tipo == "xref" and doc.xref_get_key(xref, "T")[0] == "null":
        destino = int(valor.split()[0])
    doc.xref_set_key(destino, "T", pymupdf.get_pdf_str(nombre))


def poner_valor(pagina: pymupdf.Page, xref: int, valor: str | bool) -> None:
    w = _widget(pagina, xref)
    if _tipo(w) == "casilla":
        w.field_value = w.on_state() if valor else False
    else:
        w.field_value = valor
    w.update()


def borrar(pagina: pymupdf.Page, xref: int) -> None:
    pagina.delete_widget(_widget(pagina, xref))
