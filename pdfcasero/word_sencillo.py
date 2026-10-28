"""PDF → Word pensado para Google Docs: el contenido fluye de arriba abajo.

pdf2docx copia la posición exacta de cada cosa con marcos y tablas anidadas, y en
documentos con mucho diseño (facturas) Google Docs lo descoloca. Aquí se hace
como los conversores web (iLovePDF):

- La página se corta en franjas horizontales. Si en una franja hay cosas lado a
  lado (datos a la izquierda, dirección a la derecha), se ponen en una tabla
  invisible con una columna para cada una; si no, como párrafos normales.
- Las tablas del PDF pasan a tablas de verdad, con su fondo gris y los importes
  alineados a la derecha.
- Gráficas, logotipos, códigos de barras y texto girado pasan como imagen.
- La separación vertical entre renglones se copia del PDF para que las columnas
  queden alineadas.
"""

from __future__ import annotations

import io
import re

import pymupdf
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .conversion import _clave_fuente, preparar_para_word

MAX_ESPACIO = 24  # pt: los huecos más grandes del PDF se acortan


# --- Piezas de la página -----------------------------------------------------------
class Pieza:
    """Algo que ocupa un rectángulo de la página: un renglón, una tabla o una imagen."""

    def __init__(self, tipo, rect, datos=None, fondo=None):
        self.tipo, self.rect, self.datos, self.fondo = tipo, pymupdf.Rect(rect), datos, fondo


def _dentro(r: pymupdf.Rect, zonas) -> bool:
    centro = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
    return any(centro in z for z in zonas)


def _rgb(color):
    if not color or len(color) != 3:
        return None
    r, g, b = (max(0, min(255, round(c * 255))) for c in color)
    return None if (r, g, b) == (255, 255, 255) else f"{r:02X}{g:02X}{b:02X}"


def _fondos(pagina):
    """Rectángulos rellenos de color (fondos grises de títulos y tablas)."""
    fondos = []
    for d in pagina.get_drawings():
        color = _rgb(d.get("fill"))
        r = d["rect"]
        if color and r.width > 20 and r.height > 5:
            fondos.append((r, color))
    return fondos


def _fondo_de(rect, fondos):
    caja = _caja_fondo(rect, fondos)
    return caja[1] if caja else None


def _caja_fondo(rect, fondos):
    """El rectángulo de color más pequeño que hay debajo de `rect`, con su color."""
    centro = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
    dentro = [(r.get_area(), k) for k, (r, c) in enumerate(fondos) if centro in r]
    return fondos[min(dentro)[1]] if dentro else None


def _graficas(pagina, tablas, fondos):
    """Zonas con muchos trazos (gráficas, dibujos) que no son tablas ni fondos: van como imagen."""
    zonas = []
    for r in pagina.cluster_drawings():
        r = pymupdf.Rect(r)
        if r.height < 25 or r.width < 25:
            continue
        if any(r.intersects(t) and (r & t).get_area() > 0.5 * r.get_area() for t in tablas):
            continue
        if any(abs(r.x0 - f.x0) < 3 and abs(r.y0 - f.y0) < 3 and abs(r.x1 - f.x1) < 3 for f, _ in fondos):
            continue
        trazos = sum(1 for d in pagina.get_drawings() if pymupdf.Rect(d["rect"]) in r + (-1, -1, 1, 1))
        if trazos >= 8:
            zonas.append(r)
    # Que la imagen no corte el texto que toca la gráfica (título, ejes, leyenda)
    lineas = [
        pymupdf.Rect(linea["bbox"])
        for b in pagina.get_text("dict")["blocks"]
        for linea in b.get("lines", [])
    ]
    for i, r in enumerate(zonas):
        cambia = True
        while cambia:
            cambia = False
            for linea in lineas:
                if linea.intersects(r + (-2, -2, 2, 2)) and linea not in r and linea.width < 2 * r.width:
                    r |= linea
                    cambia = True
        zonas[i] = r
    return zonas


def _tabla_valida(pagina, tabla, palabras) -> bool:
    """Una tabla mal detectada mete varias columnas en una celda: renglones con huecos grandes."""
    x0, y0, x1, y1 = tabla.bbox
    dentro = [
        ((w[0] + w[2]) / 2, (w[1] + w[3]) / 2, w[0], w[2])
        for w in palabras
        if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1
    ]
    for fila in tabla.rows:
        if sum(1 for c in fila.cells if c) < 2:
            continue  # título que ocupa toda la fila (celdas unidas)
        for c in fila.cells:
            if not c:
                continue
            renglones = {}
            for cx, cy, wx0, wx1 in dentro:
                if c[0] <= cx <= c[2] and c[1] <= cy <= c[3]:
                    renglones.setdefault(round(cy / 2), []).append((wx0, wx1))
            for ws in renglones.values():
                ws.sort()
                if any(b[0] - a[1] > 12 for a, b in zip(ws, ws[1:])):
                    return False
    return True


def _piezas(pagina):
    fondos = _fondos(pagina)
    palabras = pagina.get_text("words")
    try:  # sin la IA de maquetación de PyMuPDF (no va en el instalador): igual en todos los PC
        encontradas = pagina.find_tables(use_layout=False).tables
    except TypeError:  # PyMuPDF antiguo
        encontradas = pagina.find_tables().tables
    tablas = [t for t in encontradas if _tabla_valida(pagina, t, palabras)]
    zonas_tabla = [pymupdf.Rect(t.bbox) for t in tablas]
    graficas = _graficas(pagina, zonas_tabla, fondos)
    piezas = [Pieza("tabla", t.bbox, t, _fondo_de(pymupdf.Rect(t.bbox), fondos)) for t in tablas]
    piezas += [Pieza("imagen", g) for g in graficas]
    ocupado = zonas_tabla + graficas
    for img in pagina.get_image_info():
        caja = pymupdf.Rect(img["bbox"]) & pagina.rect
        if caja.is_empty or caja.width < 6 or caja.height < 4 or _dentro(caja, ocupado):
            continue
        if caja.height > 4 * caja.width and caja.width < 30:
            continue  # texto girado del margen: va como texto al final de la página
        piezas.append(Pieza("imagen", caja))
    # Renglones: trozos de texto horizontales a la misma altura
    trozos = []
    for bloque in pagina.get_text("dict")["blocks"]:
        for linea in bloque.get("lines", []):
            spans = [s for s in linea["spans"] if s["text"].strip()]
            if not spans or abs(linea["dir"][0] - 1) > 0.01:
                continue
            r = pymupdf.Rect(linea["bbox"])
            if _dentro(r, ocupado):
                continue
            trozos.append((r, spans))
    trozos.sort(key=lambda t: (round(t[0].y0), t[0].x0))
    for r, spans in trozos:
        caja = _caja_fondo(r, fondos)
        pieza = Pieza("texto", r, spans, caja[1] if caja else None)
        pieza.caja = caja[0] if caja else None
        piezas.append(pieza)
    return piezas


# --- Franjas y columnas -------------------------------------------------------------
def _franjas(piezas):
    """Agrupa piezas que se solapan en vertical (lo que va lado a lado)."""
    franjas = []
    for p in sorted(piezas, key=lambda p: p.rect.y0):
        alto = p.rect.height
        margen = -min(2.0, alto * 0.2)  # tocarse apenas no cuenta
        if franjas and p.rect.y0 < franjas[-1]["y1"] + margen:
            franjas[-1]["piezas"].append(p)
            franjas[-1]["y1"] = max(franjas[-1]["y1"], p.rect.y1)
        else:
            franjas.append({"y0": p.rect.y0, "y1": p.rect.y1, "piezas": [p]})
    return franjas


def _columnas(piezas, hueco=40):
    """Separa las piezas de una franja en columnas cuando hay un hueco claro entre ellas."""
    tramos = []
    for p in sorted(piezas, key=lambda p: p.rect.x0):
        # Junto a una imagen o gráfica basta un hueco pequeño para ir en otra columna
        con_dibujo = p.tipo != "texto" or (tramos and any(q.tipo != "texto" for q in tramos[-1][2]))
        dos_tablas = p.tipo == "tabla" and tramos and any(q.tipo == "tabla" for q in tramos[-1][2])
        separa = 3 if dos_tablas else 10 if con_dibujo else hueco
        if tramos and p.rect.x0 < tramos[-1][1] + separa:
            tramos[-1][1] = max(tramos[-1][1], p.rect.x1)
            tramos[-1][2].append(p)
        else:
            tramos.append([p.rect.x0, p.rect.x1, [p]])
    # Dos columnas cuyos renglones van a la misma altura (etiqueta y valor) son en
    # realidad una sola: se escriben en el mismo renglón con un tabulador
    juntos = []
    for t in tramos:
        if juntos and _alineadas(juntos[-1][2], t[2]):
            juntos[-1][1] = max(juntos[-1][1], t[1])
            juntos[-1][2].extend(t[2])
        else:
            juntos.append(t)
    return juntos


def _alineadas(izquierda, derecha) -> bool:
    centros = [(p.rect.y0 + p.rect.y1) / 2 for p in izquierda if p.tipo == "texto"]
    textos = [p for p in derecha if p.tipo == "texto"]
    if not textos or len(textos) != len(derecha):
        return False
    casan = sum(1 for p in textos if any(abs((p.rect.y0 + p.rect.y1) / 2 - c) < 2 for c in centros))
    return casan >= 0.8 * len(textos)


def _filas_de_texto(piezas):
    """Junta los trozos de texto (y las imágenes) que están a la misma altura: etiqueta y valor."""
    filas = []
    for p in sorted(piezas, key=lambda p: (p.rect.y0, p.rect.x0)):
        medio = (p.rect.y0 + p.rect.y1) / 2
        for f in filas:
            if f[0].rect.y0 - 1 <= medio <= f[0].rect.y1 + 1:
                f.append(p)
                break
        else:
            filas.append([p])
    for f in filas:
        f.sort(key=lambda p: p.rect.x0)
    return filas


# --- Escribir en Word ---------------------------------------------------------------
class Escritor:
    def __init__(self, fuentes):
        from docx import Document
        from docx.shared import Pt

        self.Pt = Pt
        self.doc = Document()
        normal = self.doc.styles["Normal"]
        normal.font.name = "Arial"
        normal.font.size = Pt(10)
        normal.paragraph_format.space_after = Pt(0)
        normal.paragraph_format.space_before = Pt(0)
        normal.paragraph_format.line_spacing = 1.0  # la plantilla trae 1,15 y la hoja crece
        self.fuentes = fuentes  # factor de tamaño por fuente (Arial es más ancha)

    def _sombrear(self, elemento, color):
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        if not color:
            return
        propiedades = elemento.get_or_add_tcPr() if hasattr(elemento, "get_or_add_tcPr") else elemento.get_or_add_pPr()
        sombra = OxmlElement("w:shd")
        sombra.set(qn("w:val"), "clear")
        sombra.set(qn("w:color"), "auto")
        sombra.set(qn("w:fill"), color)
        propiedades.append(sombra)

    def _tamano(self, span):
        factor = self.fuentes.get(_clave_fuente(span["font"]), (None, 1.0))[1]
        return max(5.5, round(span["size"] * factor * 2) / 2)

    def spans(self, p, spans):
        from docx.shared import RGBColor

        anterior = None
        for span in spans:
            if anterior is not None:
                hueco = span["bbox"][0] - anterior["bbox"][2]
                pegado = anterior["text"].endswith(" ") or span["text"].startswith(" ")
                if hueco > span["size"] * 0.15 and not pegado:
                    p.add_run(" ")
            run = p.add_run(span["text"])
            run.bold = bool(span["flags"] & 16) or "bold" in span["font"].lower()
            run.italic = bool(span["flags"] & 2)
            run.font.size = self.Pt(self._tamano(span))
            color = span.get("color", 0)
            if color:
                run.font.color.rgb = RGBColor((color >> 16) & 255, (color >> 8) & 255, color & 255)
            anterior = span

    def _foto(self, p, pieza, ancho_max):
        foto = self.pagina.get_pixmap(clip=pieza.rect, dpi=150)
        ancho = pieza.rect.width if ancho_max is None else max(10, min(pieza.rect.width, ancho_max))
        p.add_run().add_picture(io.BytesIO(foto.tobytes("png")), width=self.Pt(ancho))

    def fila(self, contenedor, fila, x_izq, espacio_antes):
        """Un renglón: el primer trozo con su sangría y los demás en tabuladores, como en el PDF."""
        con_fondo = next((pz for pz in fila if pz.fondo), None)
        caja = getattr(con_fondo, "caja", None) if con_fondo else None
        ancho = getattr(self, "ancho_columna", None)
        misma_caja = caja is not None and caja == getattr(self, "_caja_previa", None)
        if caja is not None and not misma_caja and espacio_antes > 2:
            # El hueco de encima va en blanco: con «espacio antes» el gris lo taparía
            self.contenedor_parrafo(contenedor, espacio_antes)
            espacio_antes = 0
        self._caja_previa = caja
        p = contenedor.add_paragraph()
        formato = p.paragraph_format
        formato.space_before = self.Pt(max(0, min(espacio_antes, MAX_ESPACIO)))
        inicio = fila[0].rect.x0
        if caja is not None and inicio - caja.x0 > 4:
            inicio = caja.x0 + 2  # el gris empieza donde empezaba la caja; el texto, en su tabulador
        formato.left_indent = self.Pt(max(0, min(inicio - x_izq, 400)))
        for k, pieza in enumerate(fila):
            if k or pieza.rect.x0 - inicio > 4:
                if k and _es_importe(pieza):  # números alineados por la derecha, como en el PDF
                    formato.tab_stops.add_tab_stop(self.Pt(max(0, pieza.rect.x1 - x_izq)), WD_TAB_ALIGNMENT.RIGHT)
                else:
                    formato.tab_stops.add_tab_stop(self.Pt(max(0, pieza.rect.x0 - x_izq)))
                p.add_run("\t")
            if pieza.tipo == "imagen":
                usado = pieza.rect.x0 - x_izq
                self._foto(p, pieza, ancho_max=(ancho or 9999) - max(0, usado))
            else:
                self.spans(p, pieza.datos)
        tamanos = [self._tamano(sp) for pz in fila if pz.tipo == "texto" for sp in pz.datos]
        if tamanos:
            _tamano_marca(p, max(tamanos))
        if con_fondo:
            self._sombrear(p._p, con_fondo.fondo)
            if caja is not None and ancho:  # que el gris acabe donde acababa en el PDF
                formato.right_indent = self.Pt(max(0, min(x_izq + ancho - caja.x1, ancho - 40)))
        return p

    def imagen(self, contenedor, pagina, pieza, x_izq, ancho_max, espacio_antes):
        foto = pagina.get_pixmap(clip=pieza.rect, dpi=150)
        p = contenedor.add_paragraph()
        p.paragraph_format.space_before = self.Pt(max(0, min(espacio_antes, MAX_ESPACIO)))
        sangria = max(0, min(pieza.rect.x0 - x_izq, ancho_max - 20))
        p.paragraph_format.left_indent = self.Pt(sangria)
        ancho = max(10, min(pieza.rect.width, ancho_max - sangria))
        p.add_run().add_picture(io.BytesIO(foto.tobytes("png")), width=self.Pt(ancho))
        return p

    def tabla(self, contenedor, pagina, pieza, fondos, espacio_antes):
        tabla = pieza.datos
        filas, rects = [], []
        palabras = pagina.get_text("words", clip=tabla.bbox)
        inicios = [
            min((f.cells[j][0] for f in tabla.rows if j < len(f.cells) and f.cells[j]), default=None)
            for j in range(tabla.col_count)
        ]
        for fila in tabla.rows:
            textos = [_texto_celda(palabras, c) if c else "" for c in fila.cells]
            celdas = [pymupdf.Rect(c) if c else None for c in fila.cells]
            if fila.cells and fila.cells[0] and not any(fila.cells[1:]) and len(fila.cells) > 1:
                # Celda que ocupa toda la fila (títulos de columna): cada palabra a su columna
                textos = _repartir(palabras, pymupdf.Rect(fila.cells[0]), inicios)
                celdas = [pymupdf.Rect(fila.cells[0])] * len(fila.cells)
            filas.append(textos)
            rects.append(celdas)
        usadas = [j for j in range(tabla.col_count) if any(j < len(f) and f[j] for f in filas)]
        indices = [i for i, f in enumerate(filas) if any(f[j] for j in usadas if j < len(f))]
        if not usadas or not indices:
            return None
        if espacio_antes > 2:
            self.contenedor_parrafo(contenedor, espacio_antes)
        t = contenedor.add_table(rows=len(indices), cols=len(usadas))
        t.autofit = False  # anchos fijos, los del PDF
        negritas = {
            " ".join(s["text"].split())
            for b in pagina.get_text("dict", clip=tabla.bbox)["blocks"]
            for l in b.get("lines", [])
            for s in l["spans"]
            if "bold" in s["font"].lower() or s["flags"] & 16
        }
        tamano = 9
        for b in pagina.get_text("dict", clip=tabla.bbox)["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    tamano = self._tamano(s)
                    break
        for k, i in enumerate(indices):
            celdas = t.rows[k].cells
            for m, j in enumerate(usadas):
                texto = filas[i][j] if j < len(filas[i]) else ""
                celda = celdas[m]
                p = celda.paragraphs[0]
                for n, linea in enumerate(texto.splitlines()):
                    if n:
                        p.add_run().add_break()
                    limpio = " ".join(linea.split())
                    run = p.add_run(limpio)
                    run.font.size = self.Pt(tamano)
                    run.bold = limpio in negritas
                _tamano_marca(p, tamano)
                if texto and m > 0 and any(ch.isdigit() for ch in texto) and len(texto) < 24:
                    p.alignment = 2  # importes a la derecha
                r = rects[i][j] if j < len(rects[i]) else None
                self._sombrear(celda._tc, (_fondo_de(r, fondos) if r else None) or pieza.fondo)
        # Anchos de columna como en el PDF
        xs = [inicios[j] if inicios[j] is not None else tabla.bbox[0] for j in usadas]
        xs.append(tabla.bbox[2])
        rejilla = t._tbl.tblGrid.findall(qn("w:gridCol"))
        for m in range(len(usadas)):
            ancho = self.Pt(max(20, xs[m + 1] - xs[m]))
            rejilla[m].set(qn("w:w"), str(int(max(20, xs[m + 1] - xs[m]) * 20)))
            for celda in t.columns[m].cells:
                celda.width = ancho
        _margenes_celda(t, izquierda=1, derecha=1)
        return t

    def fondo_renglon(self, pieza) -> float:
        if pieza.tipo != "texto":
            return pieza.rect.y1
        return pieza.rect.y0 + 1.15 * max(self._tamano(sp) for sp in pieza.datos)

    def rejilla(self, contenedor, filas, x_izq, ancho, y_previo):
        """Renglones en una tabla sin bordes: cada trozo en su celda, alineado como en el PDF."""
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        caja = _caja_de(filas[0])
        if caja is not None:
            izquierda, derecha = max(caja.x0, x_izq), min(caja.x1, x_izq + ancho)
            arriba = caja.y0
        else:
            izquierda = min(p.rect.x0 for f in filas for p in f)
            derecha = x_izq + ancho
            arriba = filas[0][0].rect.y0
        if y_previo is not None and arriba - y_previo > 2:
            self.contenedor_parrafo(contenedor, arriba - y_previo)
        bordes = _columnas_rejilla(filas, izquierda, derecha)
        # La sangría de la tabla va en una primera columna vacía: Google Docs y LibreOffice
        # no respetan bien la sangría de las tablas
        hueco_izq = izquierda - x_izq > 1.5
        if hueco_izq:
            bordes = [x_izq] + bordes
        n = len(bordes) - 1
        t = contenedor.add_table(rows=len(filas), cols=n)
        t.autofit = False
        _sin_bordes(t)
        _margenes_celda(t)
        rejilla = t._tbl.tblGrid.findall(qn("w:gridCol"))
        for j in range(n):
            rejilla[j].set(qn("w:w"), str(int((bordes[j + 1] - bordes[j]) * 20)))
            for celda in t.columns[j].cells:
                celda.width = self.Pt(bordes[j + 1] - bordes[j])
        y = arriba
        for k, fila in enumerate(filas):
            espacio = max(0, min(fila[0].rect.y0 - y, MAX_ESPACIO)) if k or caja is not None else 0
            celdas = t.rows[k].cells
            usadas = {}
            for pieza in fila:
                primera_util = 1 if hueco_izq else 0
                if _es_importe(pieza):  # el importe acaba en el borde derecho de su celda
                    j = min(range(primera_util, n), key=lambda i: abs(bordes[i + 1] - pieza.rect.x1))
                else:
                    j = max([i for i in range(primera_util, n) if bordes[i] <= pieza.rect.x0 + 1] or [primera_util])
                usadas.setdefault(j, []).append(pieza)
            for j, piezas in usadas.items():
                p = celdas[j].paragraphs[0]
                for m, pieza in enumerate(piezas):
                    if m:
                        p.add_run(" ")
                    if pieza.tipo == "imagen":  # logotipos uno al lado del otro
                        self._foto(p, pieza, ancho_max=bordes[j + 1] - bordes[j])
                    else:
                        self.spans(p, pieza.datos)
                primera, ultima = piezas[0], piezas[-1]
                if len(fila) == 1 and caja is not None and abs(
                    (primera.rect.x0 + primera.rect.x1) / 2 - (caja.x0 + caja.x1) / 2
                ) < 6 and primera.rect.x0 - caja.x0 > 30:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER  # título centrado en su barra
                elif _es_importe(primera) and len(piezas) == 1:
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    p.paragraph_format.right_indent = self.Pt(max(0, min(bordes[j + 1] - ultima.rect.x1, 40)))
                else:
                    p.paragraph_format.left_indent = self.Pt(max(0, min(primera.rect.x0 - bordes[j], 60)))
            tamanos = [self._tamano(sp) for pz in fila if pz.tipo == "texto" for sp in pz.datos]
            for j in range(n):
                p = celdas[j].paragraphs[0]
                p.paragraph_format.space_before = self.Pt(espacio)
                _tamano_marca(p, max(tamanos) if tamanos else 8)
                if caja is not None and not (hueco_izq and j == 0):
                    self._sombrear(celdas[j]._tc, _fondo_caja(fila))
            # Un trozo largo que no cabe en su celda ocupa también las vacías de su derecha
            for j in sorted(usadas, reverse=True):
                fin = max(p.rect.x1 for p in usadas[j])
                hasta = j
                while hasta + 1 < n and hasta + 1 not in usadas and bordes[hasta + 1] < fin - 2:
                    hasta += 1
                if hasta > j:
                    celdas[j].merge(celdas[hasta])
            y = max(self.fondo_renglon(p) for p in fila)
        if caja is not None:
            # Margen de abajo de la caja, también en gris
            hueco = max(0, min(caja.y1 - y, MAX_ESPACIO))
            if hueco > 1:
                for celda in t.rows[-1].cells:
                    celda.paragraphs[-1].paragraph_format.space_after = self.Pt(hueco)
            return caja.y1
        return y

    def contenedor_parrafo(self, contenedor, espacio):
        p = contenedor.add_paragraph()
        p.paragraph_format.space_before = self.Pt(max(0, min(espacio, MAX_ESPACIO)) - 2)
        p.paragraph_format.line_spacing = self.Pt(2)
        _tamano_marca(p, 1)
        return p


def _texto_celda(palabras, c) -> str:
    """El texto de una celda, renglón a renglón (más fiable que recortar con get_text)."""
    renglones = {}
    for w in palabras:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if c[0] <= cx <= c[2] and c[1] <= cy <= c[3]:
            renglones.setdefault((w[5], w[6]), []).append(w)
    lineas = sorted(renglones.values(), key=lambda ws: (min(w[1] for w in ws), min(w[0] for w in ws)))
    return "\n".join(" ".join(w[4] for w in sorted(ws, key=lambda w: w[0])) for ws in lineas)


def _repartir(palabras, celda, inicios) -> list[str]:
    """Reparte las palabras de una celda unida entre las columnas según dónde empiezan."""
    textos = [[] for _ in inicios]
    for w in sorted(palabras, key=lambda w: (round(w[1]), w[0])):
        if not celda.contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)):
            continue
        j = max([k for k, x in enumerate(inicios) if x is not None and x <= w[0] + 2] or [0])
        textos[j].append(w[4])
    if sum(1 for t in textos if t) < 2:  # un título de verdad: en la primera celda
        return [" ".join(sum(textos, []))] + [""] * (len(inicios) - 1)
    return [" ".join(t) for t in textos]


def _es_importe(pieza) -> bool:
    if pieza.tipo != "texto":
        return False
    texto = "".join(sp["text"] for sp in pieza.datos).strip()
    # Importes de verdad (824,10 · 1.028,26€ · 21%), no números de cuenta ni fechas
    return bool(texto) and len(texto) < 20 and (
        re.fullmatch(r"[-+]?\d[\d.]*,\d+\s?(€|%)?", texto) is not None
        or re.fullmatch(r"[-+]?[\d.,]+\s?(€|%)", texto) is not None
    )


def _tamano_marca(parrafo, tamano):
    """La marca de fin de párrafo también cuenta para la altura del renglón."""
    ppr = parrafo._p.get_or_add_pPr()
    rpr = ppr.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        ppr.append(rpr)
    for etiqueta in ("w:sz", "w:szCs"):
        sz = OxmlElement(etiqueta)
        sz.set(qn("w:val"), str(max(2, round(tamano * 2))))
        rpr.append(sz)


def _margenes_celda(tabla, izquierda=0, derecha=0):
    """Márgenes interiores de las celdas en puntos (arriba y abajo, ninguno)."""
    margenes = OxmlElement("w:tblCellMar")
    for lado, valor in (("top", 0), ("left", izquierda), ("bottom", 0), ("right", derecha)):
        m = OxmlElement(f"w:{lado}")
        m.set(qn("w:w"), str(int(valor * 20)))
        m.set(qn("w:type"), "dxa")
        margenes.append(m)
    tabla._tbl.tblPr.append(margenes)


def _sin_bordes(tabla):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tblPr = tabla._tbl.tblPr
    bordes = OxmlElement("w:tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{lado}")
        b.set(qn("w:val"), "nil")
        bordes.append(b)
    tblPr.append(bordes)


def _fondo_caja(fila):
    return next((p.fondo for p in fila if p.fondo), None)


def _caja_de(fila):
    return next((getattr(p, "caja", None) for p in fila if getattr(p, "caja", None) is not None), None)


def _es_de_rejilla(fila) -> bool:
    if any(p.tipo != "texto" for p in fila):
        return False  # logotipos y demás imágenes: en su párrafo (Google los coloca bien)
    return len(fila) > 1 or _caja_de(fila) is not None


def _columnas_rejilla(filas, izquierda, derecha):
    """Bordes de las columnas de una rejilla: los textos empiezan donde empiezan y los
    importes acaban donde acaban (alineados a la derecha), como en el PDF."""
    anclas = []  # [es_importe, x, x0 mínimo, x1 máximo]
    for fila in filas:
        for p in fila:
            derecha_p = _es_importe(p)
            x = p.rect.x1 if derecha_p else p.rect.x0
            for a in anclas:
                if a[0] == derecha_p and abs(a[1] - x) < 5:
                    a[2], a[3] = min(a[2], p.rect.x0), max(a[3], p.rect.x1)
                    break
            else:
                anclas.append([derecha_p, x, p.rect.x0, p.rect.x1])
    anclas.sort(key=lambda a: a[2])
    # Si dos anclas se pisan, se quedan en una sola columna
    juntas = []
    for a in anclas:
        if juntas and a[2] < juntas[-1][3] - 2:
            juntas[-1][3] = max(juntas[-1][3], a[3])
            juntas[-1][0] = juntas[-1][0] and a[0]
        else:
            juntas.append(list(a))
    bordes = [izquierda]
    for i in range(len(juntas) - 1):
        a, b = juntas[i], juntas[i + 1]
        corte = a[3] + 1 if a[0] or b[0] else b[2]
        bordes.append(max(bordes[-1] + 8, min(corte, b[2])))
    final = max(derecha, juntas[-1][3] + 1)
    if juntas[-1][0] and final - juntas[-1][3] > 4:
        bordes.append(juntas[-1][3] + 1)  # hueco vacío a la derecha del último importe
    bordes.append(max(final, bordes[-1] + 8))
    return bordes


def _sigue_parrafo(anterior, fila, ancho):
    """¿Este renglón continúa el párrafo anterior (texto que ocupaba varias líneas)?"""
    if not anterior or len(anterior) != 1 or len(fila) != 1:
        return False
    if anterior[0].tipo != "texto" or fila[0].tipo != "texto":
        return False
    a, b = anterior[0], fila[0]
    alto = a.rect.height
    return (
        abs(a.rect.x0 - b.rect.x0) < 3
        and 0 <= b.rect.y0 - a.rect.y1 < 0.8 * alto
        and abs(a.datos[0]["size"] - b.datos[0]["size"]) < 0.6
        and a.rect.width > 0.6 * ancho
    )


def _escribir_piezas(esc, contenedor, pagina, piezas, fondos, y_previo, x_izq, ancho, anidado=False):
    """Escribe las piezas de una columna, de arriba abajo, copiando los huecos."""
    textos = [p for p in piezas if p.tipo in ("texto", "imagen")]
    elementos = [(f[0].rect.y0, "fila", f) for f in _filas_de_texto(textos)]
    elementos += [(p.rect.y0, p.tipo, p) for p in piezas if p.tipo == "tabla"]
    elementos.sort(key=lambda e: e[0])
    # Renglones con varios trozos (etiqueta y valor, importes) o con fondo de color van en
    # tablas sin bordes, como hace iLovePDF: Google Docs coloca mal los tabuladores
    agrupados = []
    for e in elementos:
        # Dentro de una celda no: Google Docs pierde el texto de las tablas dentro de tablas
        if e[1] == "fila" and not anidado and _es_de_rejilla(e[2]):
            previo = agrupados[-1] if agrupados else None
            if (
                previo is not None and previo[1] == "rejilla"
                and _caja_de(previo[2][-1]) == _caja_de(e[2])
                and e[2][0].rect.y0 - max(p.rect.y1 for p in previo[2][-1]) < 20
            ):
                previo[2].append(e[2])
                continue
            agrupados.append((e[0], "rejilla", [e[2]]))
        else:
            agrupados.append(e)
    elementos = agrupados
    parrafo, fila_anterior = None, None
    for y0, tipo, obj in elementos:
        hueco = y0 - y_previo if y_previo is not None else 0
        if tipo == "rejilla":
            parrafo, fila_anterior = None, None
            esc._caja_previa = None
            y_previo = esc.rejilla(contenedor, obj, x_izq, ancho, y_previo)
            continue
        if tipo == "fila":
            esc.ancho_columna = ancho
            if parrafo is not None and _sigue_parrafo(fila_anterior, obj, ancho):
                parrafo.add_run(" ")
                esc.spans(parrafo, obj[0].datos)
            else:
                parrafo = esc.fila(contenedor, obj, x_izq, hueco)
            fila_anterior = obj
            # Donde acaba el renglón en Word (Arial ocupa 1,15 veces su tamaño), no en el PDF:
            # así los huecos no se suman a la altura de más y la hoja no crece
            y_previo = max(esc.fondo_renglon(p) for p in obj)
            continue
        parrafo, fila_anterior = None, None
        esc._caja_previa = None
        if tipo == "imagen":
            esc.imagen(contenedor, pagina, obj, x_izq, ancho, hueco)
        else:
            t = esc.tabla(contenedor, pagina, obj, fondos, hueco)
            if t is not None:
                _sin_bordes(t)
        y_previo = max(y_previo or 0, obj.rect.y1)
    return y_previo


def pdf_a_word_sencillo(datos_pdf: bytes, destino: str, paginas: list[int] | None = None, avance=None) -> None:
    """Convierte el PDF en un .docx que fluye (ver la explicación del módulo)."""
    from docx.enum.section import WD_SECTION
    from docx.shared import Pt

    if paginas is not None:  # solo las páginas elegidas: en facturas largas va mucho más rápido
        parte = pymupdf.open(stream=datos_pdf, filetype="pdf")
        parte.select(list(paginas))
        datos_pdf = parte.tobytes()
    datos, fuentes = preparar_para_word(datos_pdf)  # códigos de barras y texto girado como imagen
    pdf = pymupdf.open(stream=datos, filetype="pdf")
    original = pymupdf.open(stream=datos_pdf, filetype="pdf")
    lista = list(range(pdf.page_count))
    esc = Escritor(fuentes)
    doc = esc.doc
    for k, n in enumerate(lista):
        if avance:
            avance(k + 1, len(lista))
        pagina = pdf[n]
        esc.pagina = pagina
        seccion = doc.sections[0] if k == 0 else doc.add_section(WD_SECTION.NEW_PAGE)
        seccion.page_width, seccion.page_height = Pt(pagina.rect.width), Pt(pagina.rect.height)
        piezas = _piezas(pagina)
        izquierda = min((p.rect.x0 for p in piezas), default=36)
        derecha = max((p.rect.x1 for p in piezas), default=pagina.rect.width - 36)
        margen_izq = max(18, min(izquierda - 2, 72))
        margen_der = max(18, min(pagina.rect.width - derecha - 2, 72))
        seccion.left_margin, seccion.right_margin = Pt(margen_izq), Pt(margen_der)
        seccion.top_margin, seccion.bottom_margin = Pt(18), Pt(18)
        seccion.header_distance, seccion.footer_distance = Pt(0), Pt(6)
        ancho_util = pagina.rect.width - margen_izq - margen_der
        fondos = _fondos(pagina)
        y_previo = 18
        if k == 0 and doc.paragraphs and not doc.paragraphs[0].text:
            doc.paragraphs[0]._p.getparent().remove(doc.paragraphs[0]._p)
        # Las franjas de una sola columna seguidas se escriben juntas, para que los renglones
        # de una misma caja o lista de datos acaben en la misma tabla
        pendientes = []
        for franja in _franjas(piezas) + [None]:
            columnas = _columnas(franja["piezas"]) if franja else []
            if len(columnas) == 1:
                pendientes += columnas[0][2]
                continue
            if any(p.tipo == "tabla" for c in columnas for p in c[2]):
                # Tablas lado a lado: una debajo de otra, porque Google Docs pierde el texto
                # de las tablas metidas dentro de otra tabla
                for c in columnas:
                    pendientes += c[2]
                continue
            if pendientes:
                y_previo = _escribir_piezas(esc, doc, pagina, pendientes, fondos, y_previo, margen_izq, ancho_util)
                pendientes = []
            if franja is None:
                break
            # Lado a lado: tabla invisible con una columna por cada bloque
            if franja["y0"] - y_previo > 2:
                esc.contenedor_parrafo(doc, franja["y0"] - y_previo)
            t = doc.add_table(rows=1, cols=len(columnas))
            _sin_bordes(t)
            t.autofit = False
            limites = [margen_izq] + [
                (columnas[i][1] + columnas[i + 1][0]) / 2 for i in range(len(columnas) - 1)
            ] + [pagina.rect.width - margen_der]
            rejilla = t._tbl.tblGrid.findall(qn("w:gridCol"))
            for i, (x0, x1, contenido) in enumerate(columnas):
                celda = t.cell(0, i)
                celda.width = Pt(max(20, limites[i + 1] - limites[i]))
                rejilla[i].set(qn("w:w"), str(int(max(20, limites[i + 1] - limites[i]) * 20)))
                antes = len(celda.paragraphs)
                _escribir_piezas(
                    esc, celda, pagina, contenido, fondos, franja["y0"], limites[i], limites[i + 1] - limites[i],
                    anidado=True,
                )
                vacio = celda.paragraphs[0]
                if antes == 1 and not vacio.text and len(celda.paragraphs) > 1:
                    vacio._p.getparent().remove(vacio._p)
            # Sin márgenes interiores para que el texto quede donde estaba

            _margenes_celda(t)
            y_previo = franja["y1"]
        # El texto girado (por ejemplo, los datos legales del margen), en horizontal
        girado = [
            " ".join(s["text"] for s in linea["spans"]).strip()
            for b in original[n].get_text("dict")["blocks"]
            for linea in b.get("lines", [])
            if abs(linea["dir"][0] - 1) > 0.01
        ]
        girado = [g for g in girado if len(g) > 3]
        # Va en el pie de la página para no empujar el contenido a una hoja nueva
        pie = seccion.footer
        pie.is_linked_to_previous = False
        p = pie.paragraphs[0]
        p.text = ""
        if girado:
            run = p.add_run(" ".join(girado))
            run.font.size = Pt(5)
    doc.save(destino)
