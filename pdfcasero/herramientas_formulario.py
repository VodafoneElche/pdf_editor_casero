"""Ratón del modo Formulario: crear, mover, estirar, renombrar y borrar campos."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

TAM_ASA = 8
MIN_ARRASTRE = 3


class ControladorFormulario:
    def __init__(self, visor):
        self.visor = visor
        self.herramienta = "seleccionar"  # o "texto", "multilinea", "casilla"
        self.seleccion = None  # (página, Campo)
        self._pagina = None
        self._inicio = None
        self._rect = None  # rectángulo provisional mientras se arrastra (x0, y0, x1, y1)
        self._accion = None  # "crear", "mover" o "estirar"
        self.al_cambiar_seleccion = lambda campo: None

    @property
    def doc(self):
        return self.visor.doc

    def seleccionar(self, valor):
        self.seleccion = valor
        self.al_cambiar_seleccion(valor[1] if valor else None)
        self.visor._repintar()

    def cancelar(self):
        self._accion = self._rect = self._inicio = self._pagina = None
        self.seleccionar(None)

    def _sobre_asa(self, n, p) -> bool:
        if not self.seleccion or self.seleccion[0] != n or self.seleccion[1].tipo == "casilla":
            return False
        r = self.seleccion[1].rect
        radio = TAM_ASA / self.visor.escala
        return abs(p[0] - r.x1) <= radio and abs(p[1] - r.y1) <= radio

    def pulsar(self, n, p):
        self._pagina, self._inicio = n, p
        if self.herramienta == "seleccionar":
            if self._sobre_asa(n, p):
                self._accion = "estirar"
                return
            campo = self.doc.campo_en(n, *p)
            self.seleccionar((n, campo) if campo else None)
            self._accion = "mover" if campo else None
            if campo:
                r = campo.rect
                self._rect = (r.x0, r.y0, r.x1, r.y1)
            return
        self.seleccionar(None)
        self._accion = "crear"
        self._rect = (p[0], p[1], p[0], p[1])

    def arrastrar(self, n, p):
        if self._accion is None or n != self._pagina:
            return
        dx, dy = p[0] - self._inicio[0], p[1] - self._inicio[1]
        if self._accion == "crear":
            self._rect = (self._inicio[0], self._inicio[1], p[0], p[1])
        elif self._accion == "mover":
            r = self.seleccion[1].rect
            self._rect = (r.x0 + dx, r.y0 + dy, r.x1 + dx, r.y1 + dy)
        else:
            r = self.seleccion[1].rect
            self._rect = (r.x0, r.y0, max(r.x0 + 20, p[0]), max(r.y0 + 12, p[1]))
        self.visor._repintar()

    def soltar(self, n, p):
        accion, rect, inicio = self._accion, self._rect, self._inicio
        self._accion = self._rect = None
        if accion is None or rect is None:
            self.visor._repintar()
            return
        movido = abs(p[0] - inicio[0]) + abs(p[1] - inicio[1]) >= MIN_ARRASTRE
        if accion == "crear":
            if not movido and self.herramienta != "casilla":
                # Un clic sin arrastrar: tamaño por defecto
                ancho, alto = (220, 18) if self.herramienta == "texto" else (300, 60)
                rect = (inicio[0], inicio[1], inicio[0] + ancho, inicio[1] + alto)
            xref = self.doc.crear_campo(n, self.herramienta, rect)
            self.visor.documento_cambiado(conservar_dibujo=True)
            campo = next(c for c in self.doc.campos(n) if c.xref == xref)
            self.seleccionar((n, campo))
        elif movido and self.seleccion:
            pagina, campo = self.seleccion
            self.doc.mover_campo(pagina, campo.xref, rect)
            self.visor.documento_cambiado(conservar_dibujo=True)
            self._refrescar_seleccion()
        self.visor._repintar()

    def doble_clic(self, n, p):
        campo = self.doc.campo_en(n, *p)
        if campo is None:
            return
        self.seleccionar((n, campo))
        self.visor.pedir_nombre_campo(n, campo)

    def renombrar(self, n, campo, nombre):
        self.doc.renombrar_campo(n, campo.xref, nombre)
        self.visor.documento_cambiado(conservar_dibujo=True)
        self._refrescar_seleccion()

    def borrar_seleccion(self) -> bool:
        if not self.seleccion:
            return False
        n, campo = self.seleccion
        self.doc.borrar_campo(n, campo.xref)
        self.seleccionar(None)
        self.visor.documento_cambiado(conservar_dibujo=True)
        return True

    def _refrescar_seleccion(self):
        if not self.seleccion:
            return
        n, campo = self.seleccion
        nuevo = next((c for c in self.doc.campos(n) if c.xref == campo.xref), None)
        self.seleccionar((n, nuevo) if nuevo else None)

    def pintar(self, p: QPainter, n: int, escala: float):
        # Contorno de todos los campos de la página, para verlos aunque no tengan borde
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(120, 130, 170), 1, Qt.PenStyle.DotLine))
        for campo in self.doc.campos(n):
            r = campo.rect
            p.drawRect(QRectF(r.x0 * escala, r.y0 * escala, r.width * escala, r.height * escala))
            p.drawText(
                QRectF(r.x0 * escala, r.y0 * escala - 14, 300, 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                campo.nombre,
            )
        azul = QColor(0, 110, 230)
        if self._rect and self._pagina == n:
            x0, y0, x1, y1 = self._rect
            p.setPen(QPen(azul, 1.5, Qt.PenStyle.DashLine))
            if self._accion == "crear" and self.herramienta == "casilla":
                x1, y1 = x0 + 14, y0 + 14
            p.drawRect(QRectF(min(x0, x1) * escala, min(y0, y1) * escala, abs(x1 - x0) * escala, abs(y1 - y0) * escala))
        if self.seleccion and self.seleccion[0] == n and self._accion is None:
            r = self.seleccion[1].rect
            p.setPen(QPen(azul, 1.5))
            p.drawRect(QRectF(r.x0 * escala - 2, r.y0 * escala - 2, r.width * escala + 4, r.height * escala + 4))
            if self.seleccion[1].tipo != "casilla":
                p.setBrush(QColor(255, 255, 255))
                p.drawRect(QRectF(r.x1 * escala - TAM_ASA / 2, r.y1 * escala - TAM_ASA / 2, TAM_ASA, TAM_ASA))
