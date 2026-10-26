"""Editar texto dentro del PDF: cambiar, borrar y escribir texto nuevo.

Los PDF no guardan párrafos como un procesador de textos, sino letras sueltas
colocadas en la página. Por eso se edita línea a línea: se borra la línea
original y se escribe la nueva en el mismo sitio, con un tamaño y color
parecidos.

En los PDF escaneados (con la capa invisible del OCR) las letras que se ven
son parte de la imagen: se tapan con el color del papel y se escribe encima.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pymupdf

TAMANO_POR_DEFECTO = 12


@dataclass
class Linea:
    rect: pymupdf.Rect
    texto: str
    tamano: float
    color: tuple[float, float, float]
    fuente: str  # nombre de fuente base de PyMuPDF (helv, tiro, cour…)
    origen: pymupdf.Point
    invisible: bool  # texto de la capa del OCR: lo que se ve es la imagen


def _fuente_base(flags: int, nombre: str) -> str:
    """Elige la fuente estándar más parecida (las únicas que se pueden usar sin incrustar nada)."""
    nombre = nombre.lower()
    serif = bool(flags & pymupdf.TEXT_FONT_SERIFED) or "times" in nombre or ("serif" in nombre and "sans" not in nombre)
    mono = bool(flags & pymupdf.TEXT_FONT_MONOSPACED) or "courier" in nombre or "mono" in nombre
    negrita = bool(flags & pymupdf.TEXT_FONT_BOLD) or "bold" in nombre
    cursiva = bool(flags & pymupdf.TEXT_FONT_ITALIC) or "italic" in nombre or "oblique" in nombre
    familia = ("cour", "co") if mono else ("tiro", "ti") if serif else ("helv", "he")
    if negrita and cursiva:
        return familia[1] + "bi"
    if negrita:
        return familia[1] + "bo"
    if cursiva:
        return familia[1] + "it"
    return familia[0]


def _rgb(entero: int) -> tuple[float, float, float]:
    return ((entero >> 16) & 255) / 255, ((entero >> 8) & 255) / 255, (entero & 255) / 255


def lineas(pagina: pymupdf.Page) -> list[Linea]:
    resultado = []
    for bloque in pagina.get_text("dict")["blocks"]:
        if bloque["type"] != 0:
            continue
        for linea in bloque["lines"]:
            spans = [s for s in linea["spans"] if s["text"].strip()]
            if not spans:
                continue
            principal = max(spans, key=lambda s: len(s["text"]))
            resultado.append(
                Linea(
                    rect=pymupdf.Rect(linea["bbox"]),
                    texto="".join(s["text"] for s in linea["spans"]).strip(),
                    tamano=principal["size"],
                    color=_rgb(principal["color"]),
                    fuente=_fuente_base(principal["flags"], principal["font"]),
                    origen=pymupdf.Point(spans[0]["origin"]),
                    invisible=all(s.get("alpha", 255) == 0 for s in spans),
                )
            )
    return resultado


def linea_en(pagina: pymupdf.Page, punto: pymupdf.Point) -> Linea | None:
    for linea in lineas(pagina):
        if _margen(linea.rect).contains(punto):
            return linea
    return None


def _margen(rect: pymupdf.Rect) -> pymupdf.Rect:
    return pymupdf.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2)


def colores_imagen(pagina: pymupdf.Page, rect: pymupdf.Rect) -> tuple[tuple, tuple]:
    """Color del papel y de la tinta dentro de una zona, mirando cómo se ve la página."""
    zona = _margen(rect) & pagina.rect
    pix = pagina.get_pixmap(clip=zona, dpi=100, alpha=False, colorspace=pymupdf.csRGB)
    muestras = pix.samples
    pixeles = [tuple(muestras[i : i + 3]) for i in range(0, len(muestras), 3)]
    if not pixeles:
        return (1, 1, 1), (0, 0, 0)

    def brillo(p):
        return sum(p)

    # Papel: el color más repetido entre los más claros. Tinta: el más oscuro habitual.
    ordenados = sorted(pixeles, key=brillo)
    claros = ordenados[len(ordenados) // 2 :]
    papel = Counter(claros).most_common(1)[0][0]
    tinta = ordenados[max(0, len(ordenados) // 50)]
    return tuple(c / 255 for c in papel), tuple(c / 255 for c in tinta)


def ajustar_a_tinta(pagina: pymupdf.Page, rect: pymupdf.Rect) -> pymupdf.Rect:
    """En un escaneado, alarga la zona hasta donde llega de verdad la tinta de esa línea.

    La capa del OCR no siempre ocupa el ancho exacto de las letras de la imagen,
    y al tapar la línea podían quedar restos a los lados.
    """
    alto = rect.height
    banda = pymupdf.Rect(pagina.rect.x0, rect.y0 + alto * 0.1, pagina.rect.x1, rect.y1 - alto * 0.1) & pagina.rect
    ppp = 100
    pix = pagina.get_pixmap(clip=banda, dpi=ppp, alpha=False, colorspace=pymupdf.csGRAY)
    escala = ppp / 72
    ancho, filas, datos = pix.width, pix.height, pix.samples
    if not ancho or not filas:
        return rect
    oscuras = [any(datos[f * pix.stride + c] < 128 for f in range(filas)) for c in range(ancho)]
    hueco = max(2, int(alto * 1.2 * escala))  # espacio en blanco que corta la línea

    def col(x):
        return min(ancho - 1, max(0, int((x - banda.x0) * escala)))

    def avanzar(inicio, paso):
        ultimo, blancos, c = inicio, 0, inicio
        while 0 <= c < ancho and blancos < hueco:
            if oscuras[c]:
                ultimo, blancos = c, 0
            else:
                blancos += 1
            c += paso
        return ultimo

    derecha = avanzar(col(rect.x1), 1)
    izquierda = avanzar(col(rect.x0), -1)
    x0 = min(rect.x0, banda.x0 + izquierda / escala - 1)
    x1 = max(rect.x1, banda.x0 + (derecha + 1) / escala + 1)
    return pymupdf.Rect(x0, rect.y0, x1, rect.y1)


def _borrar(pagina: pymupdf.Page, rects: list[pymupdf.Rect], tapar: tuple | None) -> None:
    """Quita el texto de esas zonas. Si `tapar` es un color, además pinta encima (para escaneados)."""
    for r in rects:
        # Un poco más estrecho en vertical para no comerse letras de las líneas vecinas
        alto = r.height
        zona = pymupdf.Rect(r.x0, r.y0 + alto * 0.15, r.x1, r.y1 - alto * 0.15)
        pagina.add_redact_annot(zona, fill=tapar if tapar else False, cross_out=False)
        if tapar:
            # La redacción solo pinta el hueco central; tapamos también el resto de la línea
            pagina.draw_rect(r, color=None, fill=tapar, overlay=True)
    pagina.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )


def borrar_zonas(pagina: pymupdf.Page, rects: list[pymupdf.Rect], invisible: bool) -> None:
    if not rects:
        return
    tapar = None
    if invisible:
        union = pymupdf.Rect(rects[0])
        for r in rects[1:]:
            union |= r
        tapar, _ = colores_imagen(pagina, union)
        # Pequeño margen para no dejar bordes de letras de la imagen
        rects = [pymupdf.Rect(r.x0 - 1, r.y0, r.x1 + 1, r.y1) for r in rects]
    _borrar(pagina, [pymupdf.Rect(r) for r in rects], tapar)


def reemplazar_linea(pagina: pymupdf.Page, linea: Linea, texto_nuevo: str) -> None:
    """Cambia el texto de una línea. Texto vacío = borrar la línea."""
    color = linea.color
    fuente = linea.fuente
    if linea.invisible:
        zona = ajustar_a_tinta(pagina, linea.rect)
        papel, tinta = colores_imagen(pagina, zona)
        color, fuente = tinta, "helv"  # del escaneado no sabemos la fuente
        _borrar(pagina, [zona], papel)
    else:
        _borrar(pagina, [linea.rect], None)
    if texto_nuevo.strip():
        pagina.insert_text(linea.origen, texto_nuevo, fontname=fuente, fontsize=linea.tamano, color=color)


def escribir(
    pagina: pymupdf.Page,
    punto: pymupdf.Point,
    texto: str,
    tamano: float = TAMANO_POR_DEFECTO,
    color=(0, 0, 0),
    fuente: str = "helv",
) -> None:
    """Escribe texto nuevo; `punto` es la esquina superior izquierda de la primera línea."""
    if texto.strip():
        origen = pymupdf.Point(punto.x, punto.y + tamano * 0.8)
        pagina.insert_text(origen, texto, fontname=fuente, fontsize=tamano, color=color)
