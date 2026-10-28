"""Dibujos y esquemas: flechas, líneas, formas, globos, texto y lápiz.

Cada dibujo es una anotación PDF estándar, así que se ve en cualquier lector
(Adobe, Edge, Chrome…). Además guardamos en la anotación su "receta" (tipo,
puntos, color, grosor…) para poder moverla, cambiarle el tamaño o el color
más tarde: se borra y se vuelve a crear con la receta modificada.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, replace

import pymupdf

MARCA = "pdfcasero:"

TIPOS = ("flecha", "linea", "rect", "elipse", "globo", "texto", "lapiz")
TIPOS_DE_LINEA = ("flecha", "linea")
TIPOS_DE_CAJA = ("rect", "elipse", "texto")


@dataclass
class Dibujo:
    tipo: str
    a: tuple[float, float]  # punto inicial (en el globo: la punta)
    b: tuple[float, float]  # punto final o esquina opuesta
    color: tuple[float, float, float] = (0.85, 0.1, 0.1)
    grosor: float = 2.0
    relleno: bool = False
    texto: str = ""
    tam: float = 12.0
    trazos: list[list[tuple[float, float]]] = field(default_factory=list)  # lápiz
    caja: tuple[float, float, float, float] | None = None  # globo: cuadro del texto

    # --- Geometría -----------------------------------------------------------
    def rect(self) -> pymupdf.Rect:
        if self.tipo == "lapiz":
            xs = [p[0] for t in self.trazos for p in t] or [self.a[0]]
            ys = [p[1] for t in self.trazos for p in t] or [self.a[1]]
            return pymupdf.Rect(min(xs), min(ys), max(xs), max(ys))
        if self.tipo == "globo":
            r = pymupdf.Rect(self.caja_globo())
            return r | pymupdf.Point(self.a)
        return pymupdf.Rect(self.a, self.b).normalize()

    def caja_globo(self) -> pymupdf.Rect:
        if self.caja:
            return pymupdf.Rect(self.caja)
        return pymupdf.Rect(self.b[0], self.b[1], self.b[0] + 170, self.b[1] + 56)

    def movido(self, dx: float, dy: float) -> "Dibujo":
        def m(p):
            return (p[0] + dx, p[1] + dy)

        caja = None
        if self.tipo == "globo":
            c = self.caja_globo()
            caja = (c.x0 + dx, c.y0 + dy, c.x1 + dx, c.y1 + dy)
        return replace(
            self,
            a=m(self.a),
            b=m(self.b),
            trazos=[[m(p) for p in t] for t in self.trazos],
            caja=caja,
        )

    def asas(self) -> list[tuple[float, float]]:
        """Puntos que se pueden arrastrar para cambiar la forma."""
        if self.tipo in TIPOS_DE_LINEA:
            return [self.a, self.b]
        if self.tipo in TIPOS_DE_CAJA:
            r = self.rect()
            return [(r.x0, r.y0), (r.x1, r.y1)]
        if self.tipo == "globo":
            c = self.caja_globo()
            return [self.a, (c.x1, c.y1)]
        return []

    def con_asa(self, indice: int, p: tuple[float, float]) -> "Dibujo":
        """Copia con el asa `indice` llevada al punto p."""
        if self.tipo in TIPOS_DE_LINEA:
            return replace(self, a=p) if indice == 0 else replace(self, b=p)
        if self.tipo in TIPOS_DE_CAJA:
            r = self.rect()
            if indice == 0:
                return replace(self, a=p, b=(r.x1, r.y1))
            return replace(self, a=(r.x0, r.y0), b=p)
        if self.tipo == "globo":
            if indice == 0:
                return replace(self, a=p)
            c = self.caja_globo()
            return replace(self, caja=(c.x0, c.y0, max(p[0], c.x0 + 40), max(p[1], c.y0 + 20)))
        return self

    def distancia(self, p: tuple[float, float]) -> float:
        """Distancia del punto al dibujo (0 si está encima), para seleccionarlo con un clic."""
        if self.tipo in TIPOS_DE_LINEA:
            return _dist_segmento(p, self.a, self.b)
        if self.tipo == "lapiz":
            return min(
                (_dist_segmento(p, t[i], t[i + 1]) for t in self.trazos for i in range(len(t) - 1)),
                default=math.inf,
            )
        if self.tipo == "globo":
            caja = self.caja_globo()
            return min(_dist_rect(p, caja), _dist_segmento(p, self.a, _centro(caja)))
        r = self.rect()
        if self.relleno or self.tipo == "texto":
            return _dist_rect(p, r)
        # Formas sin relleno: solo se seleccionan por el borde
        dentro = r.x0 <= p[0] <= r.x1 and r.y0 <= p[1] <= r.y1
        if dentro:
            return min(p[0] - r.x0, r.x1 - p[0], p[1] - r.y0, r.y1 - p[1])
        return _dist_rect(p, r)

    # --- Guardar dentro de la anotación --------------------------------------
    def receta(self) -> str:
        return MARCA + json.dumps(asdict(self), separators=(",", ":"))

    @staticmethod
    def desde_receta(texto: str) -> "Dibujo | None":
        if not texto or not texto.startswith(MARCA):
            return None
        datos = json.loads(texto[len(MARCA) :])
        datos["a"], datos["b"] = tuple(datos["a"]), tuple(datos["b"])
        datos["color"] = tuple(datos["color"])
        datos["trazos"] = [[tuple(p) for p in t] for t in datos.get("trazos", [])]
        if datos.get("caja"):
            datos["caja"] = tuple(datos["caja"])
        return Dibujo(**datos)


def _dist_segmento(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    largo2 = dx * dx + dy * dy
    t = 0 if largo2 == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / largo2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _dist_rect(p, r) -> float:
    dx = max(r.x0 - p[0], 0, p[0] - r.x1)
    dy = max(r.y0 - p[1], 0, p[1] - r.y1)
    return math.hypot(dx, dy)


def _centro(r) -> tuple[float, float]:
    return ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)


def _relleno_suave(color):
    """Versión clara del color para rellenar formas sin tapar lo de debajo."""
    return tuple(1 - (1 - c) * 0.25 for c in color)


# --- Crear y buscar anotaciones -------------------------------------------------
def crear(pagina: pymupdf.Page, d: Dibujo) -> pymupdf.Annot:
    if d.tipo in TIPOS_DE_LINEA:
        annot = pagina.add_line_annot(d.a, d.b)
        if d.tipo == "flecha":
            annot.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
        annot.set_colors(stroke=d.color, fill=d.color)
        annot.set_border(width=d.grosor)
    elif d.tipo in ("rect", "elipse"):
        r = d.rect()
        annot = pagina.add_rect_annot(r) if d.tipo == "rect" else pagina.add_circle_annot(r)
        annot.set_colors(stroke=d.color, fill=_relleno_suave(d.color) if d.relleno else None)
        annot.set_border(width=d.grosor)
    elif d.tipo == "lapiz":
        annot = pagina.add_ink_annot([list(t) for t in d.trazos])
        annot.set_colors(stroke=d.color)
        annot.set_border(width=d.grosor)
    elif d.tipo == "texto":
        annot = pagina.add_freetext_annot(
            d.rect(), d.texto or " ", fontsize=d.tam, fontname="helv", text_color=d.color
        )
    elif d.tipo == "globo":
        caja = d.caja_globo()
        # La línea sale del borde del cuadro más cercano a la punta
        cx = min(max(d.a[0], caja.x0), caja.x1)
        cy = min(max(d.a[1], caja.y0), caja.y1)
        annot = pagina.add_freetext_annot(
            caja,
            d.texto or " ",
            fontsize=d.tam,
            fontname="helv",
            text_color=d.color,  # en los globos el color se aplica al texto, al borde y a la flecha
            fill_color=(1, 1, 0.88),
            border_width=max(1, d.grosor / 2),
            callout=(pymupdf.Point(d.a), pymupdf.Point(cx, cy)),
            line_end=pymupdf.PDF_ANNOT_LE_CLOSED_ARROW,
        )
    else:
        raise ValueError(f"Tipo de dibujo desconocido: {d.tipo}")
    annot.set_info(subject=d.receta(), title="PDF Casero")
    annot.update()
    return annot


def dibujos(pagina: pymupdf.Page) -> list[tuple[int, Dibujo]]:
    """Dibujos hechos con PDF Casero en esta página: (xref de la anotación, dibujo)."""
    resultado = []
    for annot in pagina.annots():
        d = Dibujo.desde_receta(annot.info.get("subject", ""))
        if d:
            resultado.append((annot.xref, d))
    return resultado


def dibujo_en(pagina: pymupdf.Page, p: tuple[float, float], tolerancia: float = 5) -> tuple[int, Dibujo] | None:
    """El dibujo más cercano al punto (el de encima si hay varios)."""
    mejor, distancia = None, math.inf
    for xref, d in reversed(dibujos(pagina)):
        dist = d.distancia(p) - d.grosor / 2
        if dist <= tolerancia and dist < distancia:
            mejor, distancia = (xref, d), dist
    return mejor


def borrar(pagina: pymupdf.Page, xref: int) -> None:
    for annot in pagina.annots():
        if annot.xref == xref:
            pagina.delete_annot(annot)
            return


def reemplazar(pagina: pymupdf.Page, xref: int, d: Dibujo) -> int:
    borrar(pagina, xref)
    return crear(pagina, d).xref
