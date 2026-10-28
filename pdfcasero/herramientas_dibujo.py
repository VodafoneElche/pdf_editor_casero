"""Ratón y teclado del modo Dibujo: crear, seleccionar, mover y retocar dibujos."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from .dibujo import TIPOS_DE_CAJA, TIPOS_DE_LINEA, Dibujo

TAM_ASA = 8  # píxeles en pantalla
MIN_ARRASTRE = 3  # puntos PDF: menos que esto es un clic, no un arrastre


class ControladorDibujo:
    def __init__(self, visor):
        self.visor = visor
        self.herramienta = "seleccionar"
        self.color = (0.85, 0.1, 0.1)
        self.grosor = 2.0
        self.relleno = False
        # Selección: (página, xref, dibujo)
        self.seleccion: tuple[int, int, Dibujo] | None = None
        # Arrastre en curso
        self._pagina = None
        self._inicio = None
        self._vista_previa: Dibujo | None = None
        self._accion = None  # "crear", "mover" o ("asa", i)
        self.al_cambiar_seleccion = lambda d: None

    @property
    def doc(self):
        return self.visor.doc

    # --- Utilidades ----------------------------------------------------------
    def _nuevo(self, tipo, a, b) -> Dibujo:
        return Dibujo(tipo, a, b, color=self.color, grosor=self.grosor, relleno=self.relleno)

    def seleccionar(self, valor):
        self.seleccion = valor
        self.al_cambiar_seleccion(valor[2] if valor else None)
        self.visor._repintar()

    def cancelar(self):
        self._accion = self._vista_previa = self._inicio = self._pagina = None
        self.seleccionar(None)

    def _asa_en(self, n, p) -> int | None:
        if not self.seleccion or self.seleccion[0] != n:
            return None
        radio = TAM_ASA / self.visor.escala
        for i, (x, y) in enumerate(self.seleccion[2].asas()):
            if abs(p[0] - x) <= radio and abs(p[1] - y) <= radio:
                return i
        return None

    # --- Ratón ---------------------------------------------------------------
    def pulsar(self, n: int, p: tuple[float, float]):
        self._pagina, self._inicio = n, p
        if self.herramienta == "seleccionar":
            asa = self._asa_en(n, p)
            if asa is not None:
                self._accion, self._vista_previa = ("asa", asa), self.seleccion[2]
                return
            encontrado = self.doc.dibujo_en(n, *p)
            if encontrado:
                self.seleccionar((n, *encontrado))
                self._accion, self._vista_previa = "mover", encontrado[1]
            else:
                self.seleccionar(None)
                self._accion = None
            return
        self.seleccionar(None)
        self._accion = "crear"
        if self.herramienta == "lapiz":
            self._vista_previa = replace(self._nuevo("lapiz", p, p), trazos=[[p]])
        elif self.herramienta == "texto":
            self._accion = None
            self.visor.pedir_texto(n, p, "", lambda t: self._crear_texto(n, p, t))
        else:
            self._vista_previa = self._nuevo(self.herramienta, p, p)

    def arrastrar(self, n: int, p: tuple[float, float]):
        if self._accion is None or n != self._pagina or self._vista_previa is None:
            return
        d = self._vista_previa
        if self._accion == "crear":
            if d.tipo == "lapiz":
                self._vista_previa = replace(d, trazos=[d.trazos[0] + [p]])
            else:
                self._vista_previa = replace(d, b=p)
        elif self._accion == "mover":
            original = self.seleccion[2]
            self._vista_previa = original.movido(p[0] - self._inicio[0], p[1] - self._inicio[1])
        else:
            self._vista_previa = self.seleccion[2].con_asa(self._accion[1], p)
        self.visor._repintar()

    def soltar(self, n: int, p: tuple[float, float]):
        accion, d, inicio = self._accion, self._vista_previa, self._inicio
        self._accion = self._vista_previa = None
        if accion is None or d is None:
            return
        movido = abs(p[0] - inicio[0]) + abs(p[1] - inicio[1]) >= MIN_ARRASTRE
        if accion == "crear":
            self._terminar_creacion(n, d, movido)
        elif movido:
            pagina, xref, _ = self.seleccion
            nuevo = self.doc.cambiar_dibujo(pagina, xref, d)
            self.seleccion = (pagina, nuevo, d)
            self.visor.documento_cambiado(conservar_dibujo=True)
        self.visor._repintar()

    def doble_clic(self, n: int, p: tuple[float, float]):
        if self.herramienta != "seleccionar":
            return
        encontrado = self.doc.dibujo_en(n, *p)
        if encontrado and encontrado[1].tipo in ("texto", "globo"):
            xref, d = encontrado
            caja = d.caja_globo() if d.tipo == "globo" else d.rect()
            self.visor.pedir_texto(
                n, (caja.x0, caja.y0), d.texto, lambda t: self._cambiar_texto(n, xref, d, t), d.tam
            )

    def _terminar_creacion(self, n, d: Dibujo, movido: bool):
        if d.tipo == "lapiz":
            if len(d.trazos[0]) > 1:
                self._guardar_nuevo(n, d)
            return
        if d.tipo == "globo":
            if not movido:  # un clic: el cuadro se coloca arriba a la derecha de la punta
                d = replace(d, b=(d.a[0] + 40, d.a[1] - 80))
            self.visor.pedir_texto(n, d.b, "", lambda t: t and self._guardar_nuevo(n, replace(d, texto=t)))
            return
        if not movido:
            return
        if d.tipo in TIPOS_DE_CAJA:
            r = d.rect()
            d = replace(d, a=(r.x0, r.y0), b=(r.x1, r.y1))
        self._guardar_nuevo(n, d)

    def _crear_texto(self, n, p, texto):
        if not texto:
            return
        from pymupdf import get_text_length

        ancho = get_text_length(texto, fontname="helv", fontsize=14) + 12
        d = replace(self._nuevo("texto", p, (p[0] + ancho, p[1] + 14 * 1.6)), texto=texto, tam=14)
        self._guardar_nuevo(n, d)

    def _cambiar_texto(self, n, xref, d, texto):
        if texto == d.texto:
            return
        if not texto:
            self.doc.borrar_dibujo(n, xref)
            self.seleccion = None
        else:
            nuevo = replace(d, texto=texto)
            if d.tipo == "texto":
                from pymupdf import get_text_length

                ancho = get_text_length(texto, fontname="helv", fontsize=d.tam) + 12
                nuevo = replace(nuevo, b=(max(d.b[0], d.a[0] + ancho), d.b[1]))
            self.seleccion = (n, self.doc.cambiar_dibujo(n, xref, nuevo), nuevo)
        self.visor.documento_cambiado(conservar_dibujo=True)

    def _guardar_nuevo(self, n, d: Dibujo):
        xref = self.doc.anadir_dibujo(n, d)
        self.visor.documento_cambiado(conservar_dibujo=True)
        self.seleccionar((n, xref, d))

    # --- Cambios desde la barra ----------------------------------------------
    def aplicar_estilo(self, **cambios):
        """Cambia color, grosor o relleno de lo que se dibuje y del dibujo seleccionado."""
        for k, v in cambios.items():
            setattr(self, k, v)
        if self.seleccion:
            n, xref, d = self.seleccion
            nuevo = replace(d, **cambios)
            self.seleccion = (n, self.doc.cambiar_dibujo(n, xref, nuevo), nuevo)
            self.visor.documento_cambiado(conservar_dibujo=True)

    def borrar_seleccion(self) -> bool:
        if not self.seleccion:
            return False
        n, xref, _ = self.seleccion
        self.doc.borrar_dibujo(n, xref)
        self.seleccion = None
        self.visor.documento_cambiado(conservar_dibujo=True)
        self.al_cambiar_seleccion(None)
        return True

    # --- Pintar la vista previa y la selección -------------------------------
    def pintar(self, p: QPainter, n: int, escala: float):
        if self._vista_previa is not None and self._pagina == n:
            _pintar_dibujo(p, self._vista_previa, escala)
        if self.seleccion and self.seleccion[0] == n:
            d = self._vista_previa if self._accion in ("mover",) or isinstance(self._accion, tuple) else None
            d = d or self.seleccion[2]
            r = d.rect()
            pluma = QPen(QColor(0, 110, 230), 1, Qt.PenStyle.DashLine)
            p.setPen(pluma)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(r.x0 * escala - 4, r.y0 * escala - 4, r.width * escala + 8, r.height * escala + 8))
            p.setPen(QPen(QColor(0, 110, 230), 1))
            p.setBrush(QColor(255, 255, 255))
            for x, y in d.asas():
                p.drawRect(QRectF(x * escala - TAM_ASA / 2, y * escala - TAM_ASA / 2, TAM_ASA, TAM_ASA))


def _pintar_dibujo(p: QPainter, d: Dibujo, escala: float):
    """Vista previa aproximada mientras se arrastra (el dibujo de verdad lo pinta el PDF)."""
    color = QColor.fromRgbF(*d.color)
    p.setPen(QPen(color, max(1.0, d.grosor * escala), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)

    def q(pt):
        return QPointF(pt[0] * escala, pt[1] * escala)

    if d.tipo in TIPOS_DE_LINEA:
        p.drawLine(q(d.a), q(d.b))
    elif d.tipo == "lapiz":
        for trazo in d.trazos:
            camino = QPainterPath(q(trazo[0]))
            for pt in trazo[1:]:
                camino.lineTo(q(pt))
            p.drawPath(camino)
    else:
        r = d.caja_globo() if d.tipo == "globo" else d.rect()
        rect = QRectF(r.x0 * escala, r.y0 * escala, r.width * escala, r.height * escala)
        if d.tipo == "elipse":
            p.drawEllipse(rect)
        else:
            p.drawRect(rect)
        if d.tipo == "globo":
            p.drawLine(q(d.a), rect.center())
