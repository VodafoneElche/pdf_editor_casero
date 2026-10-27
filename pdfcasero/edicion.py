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
    exacta: bool = False  # zona de tinta medida en la imagen: no hace falta ajustarla


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


def preparar(pagina: pymupdf.Page) -> None:
    """Aísla el contenido original de la página antes de añadir nada.

    Algunos PDF (por ejemplo los de "Microsoft Print to PDF") dejan cambiado el
    sistema de coordenadas al final de la página; sin esto, lo que añadimos
    saldría desplazado o boca abajo.
    """
    if not pagina.is_wrapped:
        pagina.wrap_contents()


# --- Texto que forma parte de una imagen (escaneos, PDF "impresos") -----------
PPP_TINTA = 4  # píxeles por punto al analizar la imagen
OSCURO = 140  # gris por debajo del cual un píxel es tinta
LARGO_RAYA = 25  # puntos: una racha de tinta más larga es una raya (subrayado, renglón)


def _gris(pagina: pymupdf.Page, zona: pymupdf.Rect):
    pix = pagina.get_pixmap(clip=zona, matrix=pymupdf.Matrix(PPP_TINTA, PPP_TINTA), colorspace=pymupdf.csGRAY, alpha=False)
    return pix.width, pix.height, pix.stride, pix.samples


def _mascara_sin_rayas(ancho, alto, stride, datos):
    """Tinta de cada píxel, sin las rayas horizontales largas (subrayados y renglones)."""
    largo = LARGO_RAYA * PPP_TINTA
    filas = []
    for f in range(alto):
        fila = [datos[f * stride + c] < OSCURO for c in range(ancho)]
        c = 0
        while c < ancho:
            if fila[c]:
                inicio = c
                while c < ancho and fila[c]:
                    c += 1
                if c - inicio >= largo:
                    for k in range(inicio, c):
                        fila[k] = False
            else:
                c += 1
        filas.append(fila)
    return filas


def zona_de_tinta(pagina: pymupdf.Page, punto: pymupdf.Point) -> pymupdf.Rect | None:
    """Rectángulo de las letras dibujadas (no texto) que hay bajo el punto, o None.

    Sirve para cambiar palabras que forman parte de una imagen, como un
    formulario impreso a PDF o escaneado sin OCR. Ignora los subrayados.
    """
    zona = pymupdf.Rect(punto.x - 250, punto.y - 14, punto.x + 250, punto.y + 14) & pagina.rect
    if zona.is_empty:
        return None
    ancho, alto, stride, datos = _gris(pagina, zona)
    if not ancho or not alto:
        return None
    tinta = _mascara_sin_rayas(ancho, alto, stride, datos)
    cx = int((punto.x - zona.x0) * PPP_TINTA)
    cy = int((punto.y - zona.y0) * PPP_TINTA)
    # 1. Filas con tinta cerca del clic: dan el alto de la línea de letras
    margen = 4 * PPP_TINTA
    cerca = range(max(0, cx - margen), min(ancho, cx + margen + 1))
    con_tinta = [any(tinta[f][c] for c in cerca) for f in range(alto)]
    if not any(con_tinta[max(0, cy - margen) : cy + margen + 1]):
        return None
    hueco_v = max(2, PPP_TINTA)  # 1 pt sin tinta corta la línea
    f0 = f1 = min(range(alto), key=lambda f: abs(f - cy) if con_tinta[f] else alto * 2)
    blancos = 0
    while f0 > 0 and blancos < hueco_v:
        f0 -= 1
        blancos = 0 if con_tinta[f0] else blancos + 1
    f0 += blancos
    blancos = 0
    while f1 < alto - 1 and blancos < hueco_v:
        f1 += 1
        blancos = 0 if con_tinta[f1] else blancos + 1
    f1 -= blancos
    alto_letras = f1 - f0 + 1
    if alto_letras < 3 * PPP_TINTA or alto_letras > 40 * PPP_TINTA:
        return None  # demasiado pequeño (puntitos) o grande (un dibujo)
    # 2. Columnas con tinta en esas filas; se une lo que está cerca (letras y palabras de una frase)
    columnas = [any(tinta[f][c] for f in range(f0, f1 + 1)) for c in range(ancho)]
    hueco_h = max(2, int(alto_letras * 0.8))
    inicio = min(range(ancho), key=lambda c: abs(c - cx) if columnas[c] else ancho * 2)
    if not columnas[inicio] or abs(inicio - cx) > 3 * PPP_TINTA:
        return None
    c0 = c1 = inicio
    blancos = 0
    while c0 > 0 and blancos < hueco_h:
        c0 -= 1
        blancos = 0 if columnas[c0] else blancos + 1
    c0 += blancos
    blancos = 0
    while c1 < ancho - 1 and blancos < hueco_h:
        c1 += 1
        blancos = 0 if columnas[c1] else blancos + 1
    c1 -= blancos
    return pymupdf.Rect(
        zona.x0 + c0 / PPP_TINTA, zona.y0 + f0 / PPP_TINTA, zona.x0 + (c1 + 1) / PPP_TINTA, zona.y0 + (f1 + 1) / PPP_TINTA
    )


def linea_de_imagen(pagina: pymupdf.Page, punto: pymupdf.Point) -> Linea | None:
    """Como linea_en, pero para letras que son parte de una imagen."""
    rect = zona_de_tinta(pagina, punto)
    if rect is None:
        return None
    _, tinta = colores_imagen(pagina, rect)
    # Las mayúsculas ocupan ~0,7 del tamaño de letra; las minúsculas con rabito algo más
    tamano = max(5.0, min(40.0, rect.height / 0.72))
    return Linea(
        rect=rect,
        texto=leer_zona(pagina, rect),
        tamano=tamano,
        color=tinta,
        fuente="helv",
        origen=pymupdf.Point(rect.x0, rect.y1 - rect.height * 0.04),
        invisible=True,
        exacta=True,
    )


def leer_zona(pagina: pymupdf.Page, rect: pymupdf.Rect) -> str:
    """OCR de una zona pequeña, para mostrar qué pone. Vacío si no se puede."""
    try:
        from .ocr import IDIOMAS, buscar_tessdata

        tessdata = buscar_tessdata()
        if tessdata is None:
            return ""
        zona = pymupdf.Rect(rect.x0 - 3, rect.y0 - 3, rect.x1 + 3, rect.y1 + 1) & pagina.rect
        pix = pagina.get_pixmap(clip=zona, dpi=300, colorspace=pymupdf.csGRAY, alpha=False)
        hoja = pymupdf.open()
        p = hoja.new_page(width=zona.width, height=zona.height)
        p.insert_image(p.rect, pixmap=pix)
        tp = p.get_textpage_ocr(dpi=300, full=True, language="+".join(IDIOMAS), tessdata=str(tessdata))
        texto = " ".join(p.get_text("text", textpage=tp).split())
        # Restos de subrayados y bordes que el OCR confunde con letras
        return texto.translate(str.maketrans("", "", "|_—")).strip(" -.")
    except Exception:
        return ""


def renglon_cercano(pagina: pymupdf.Page, punto: pymupdf.Point) -> float | None:
    """Altura (y) de la raya horizontal sobre la que se quiere escribir, si la hay.

    En los formularios se escribe encima de una línea ("Fdo.: ______"). Busca
    una raya justo debajo del clic (o en el mismo clic) y devuelve su altura.
    """
    zona = pymupdf.Rect(punto.x - 20, punto.y - 4, punto.x + 20, punto.y + 16) & pagina.rect
    if zona.is_empty:
        return None
    ancho, alto, stride, datos = _gris(pagina, zona)
    if not ancho:
        return None
    for f in range(alto):
        oscuros = sum(1 for c in range(ancho) if datos[f * stride + c] < OSCURO)
        if oscuros >= ancho * 0.9:
            return zona.y0 + f / PPP_TINTA
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
    preparar(pagina)
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
    preparar(pagina)
    color = linea.color
    fuente = linea.fuente
    if linea.invisible:
        if linea.exacta:  # zona medida en la imagen: un pelín más grande, sin bajar hasta el subrayado
            r = linea.rect
            zona = pymupdf.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 1, r.y1 + 0.3)
        else:
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
        preparar(pagina)
        origen = pymupdf.Point(punto.x, punto.y + tamano * 0.8)
        pagina.insert_text(origen, texto, fontname=fuente, fontsize=tamano, color=color)
