"""Vista continua de páginas con zoom. Solo dibuja las páginas que se ven."""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QWheelEvent
from PySide6.QtWidgets import QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .documento import Documento, Resultado

# 100 % de zoom = tamaño real en una pantalla de 96 ppp
PUNTOS_A_PIXELES = 96 / 72
ZOOM_MIN, ZOOM_MAX = 0.25, 5.0
MARGEN = 16
MAX_CACHE = 24


class PaginaWidget(QWidget):
    def __init__(self, visor: "VisorPDF", indice: int):
        super().__init__()
        self.visor = visor
        self.indice = indice
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        img = self.visor.imagen_pagina(self.indice)
        if img is not None:
            p.drawImage(QRectF(self.rect()), img)
        escala = self.visor.escala
        for res, activo in self.visor.resaltados_de(self.indice):
            color = QColor(255, 140, 0, 120) if activo else QColor(255, 230, 0, 100)
            r = res.rect
            p.fillRect(QRectF(r.x0 * escala, r.y0 * escala, r.width * escala, r.height * escala), color)
        p.end()


class VisorPDF(QScrollArea):
    paginaCambiada = Signal(int)
    zoomCambiado = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Documento | None = None
        self.zoom = 1.0
        self.ajustar_ancho = True
        self._cache: OrderedDict[tuple[int, float], QImage] = OrderedDict()
        self._paginas: list[PaginaWidget] = []
        self._resultados: list[Resultado] = []
        self._activo = -1
        self._pagina_actual = 0

        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setObjectName("visor")
        self._contenedor = QWidget()
        self._contenedor.setObjectName("fondoVisor")
        self._layout = QVBoxLayout(self._contenedor)
        self._layout.setContentsMargins(MARGEN, MARGEN, MARGEN, MARGEN)
        self._layout.setSpacing(MARGEN)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setWidget(self._contenedor)

        self.verticalScrollBar().valueChanged.connect(self._al_desplazar)
        self._temporizador_ajuste = QTimer(self, singleShot=True, interval=60)
        self._temporizador_ajuste.timeout.connect(self._aplicar_ajuste_ancho)

    # --- Documento -------------------------------------------------------
    def cargar(self, doc: Documento | None) -> None:
        for w in self._paginas:
            w.deleteLater()
        self._paginas.clear()
        self._cache.clear()
        self._resultados, self._activo = [], -1
        self.doc = doc
        if doc is None:
            return
        for i in range(doc.num_paginas):
            w = PaginaWidget(self, i)
            self._layout.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)
            self._paginas.append(w)
        self._pagina_actual = 0
        if self.ajustar_ancho:
            self._aplicar_ajuste_ancho()
        else:
            self._redimensionar()
        self.verticalScrollBar().setValue(0)
        self.paginaCambiada.emit(0)

    @property
    def escala(self) -> float:
        """Píxeles lógicos por punto PDF."""
        return self.zoom * PUNTOS_A_PIXELES

    def imagen_pagina(self, i: int) -> QImage | None:
        if self.doc is None:
            return None
        dpr = self.devicePixelRatioF()
        clave = (i, round(self.escala * dpr, 4))
        img = self._cache.get(clave)
        if img is None:
            datos, an, al, paso = self.doc.renderizar(i, clave[1])
            img = QImage(datos, an, al, paso, QImage.Format.Format_RGB888).copy()
            img.setDevicePixelRatio(dpr)
            self._cache[clave] = img
            while len(self._cache) > MAX_CACHE:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(clave)
        return img

    # --- Zoom ------------------------------------------------------------
    def set_zoom(self, zoom: float, ajustar_ancho: bool = False) -> None:
        zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        self.ajustar_ancho = ajustar_ancho
        if abs(zoom - self.zoom) < 1e-4:
            return
        pagina = self._pagina_actual
        self.zoom = zoom
        self._redimensionar()
        self.ir_a_pagina(pagina)
        self.zoomCambiado.emit(self.zoom)

    def acercar(self):
        self.set_zoom(self.zoom * 1.2)

    def alejar(self):
        self.set_zoom(self.zoom / 1.2)

    def zoom_ajustar_ancho(self):
        self.ajustar_ancho = True
        self._aplicar_ajuste_ancho()

    def zoom_pagina_completa(self):
        if not self.doc:
            return
        an, al = self.doc.tamano_pagina(self._pagina_actual)
        vp = self.viewport().size()
        z = min((vp.width() - 2 * MARGEN) / an, (vp.height() - 2 * MARGEN) / al) / PUNTOS_A_PIXELES
        self.set_zoom(z)

    def _aplicar_ajuste_ancho(self):
        if not self.doc or not self.ajustar_ancho:
            return
        ancho_max = max(self.doc.tamano_pagina(i)[0] for i in range(min(self.doc.num_paginas, 20)))
        disponible = self.viewport().width() - 2 * MARGEN
        self.set_zoom(disponible / (ancho_max * PUNTOS_A_PIXELES), ajustar_ancho=True)
        self._redimensionar()

    def _redimensionar(self):
        if not self.doc:
            return
        for w in self._paginas:
            an, al = self.doc.tamano_pagina(w.indice)
            w.setFixedSize(round(an * self.escala), round(al * self.escala))
        self._contenedor.adjustSize()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        if self.ajustar_ancho:
            self._temporizador_ajuste.start()

    def wheelEvent(self, evento: QWheelEvent):
        if evento.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.acercar() if evento.angleDelta().y() > 0 else self.alejar()
            evento.accept()
        else:
            super().wheelEvent(evento)

    # --- Navegación ------------------------------------------------------
    @property
    def pagina_actual(self) -> int:
        return self._pagina_actual

    def ir_a_pagina(self, i: int, y_puntos: float | None = None) -> None:
        if not self._paginas:
            return
        i = max(0, min(len(self._paginas) - 1, i))
        self._contenedor.layout().activate()
        w = self._paginas[i]
        y = w.y() - MARGEN
        if y_puntos is not None:
            y = w.y() + int(y_puntos * self.escala) - self.viewport().height() // 3
        self.verticalScrollBar().setValue(y)
        self._fijar_pagina(i)

    def pagina_siguiente(self):
        self.ir_a_pagina(self._pagina_actual + 1)

    def pagina_anterior(self):
        self.ir_a_pagina(self._pagina_actual - 1)

    def _al_desplazar(self, _valor):
        if not self._paginas:
            return
        centro = self.verticalScrollBar().value() + self.viewport().height() // 2
        for w in self._paginas:
            if w.y() + w.height() + MARGEN // 2 >= centro:
                self._fijar_pagina(w.indice)
                break

    def _fijar_pagina(self, i):
        if i != self._pagina_actual:
            self._pagina_actual = i
            self.paginaCambiada.emit(i)

    # --- Resaltado de búsqueda --------------------------------------------
    def mostrar_resultados(self, resultados: list[Resultado], activo: int) -> None:
        self._resultados, self._activo = resultados, activo
        if 0 <= activo < len(resultados):
            r = resultados[activo]
            self.ir_a_pagina(r.pagina, r.rect.y0)
        self._contenedor.update()
        for w in self._paginas:
            w.update()

    def resaltados_de(self, i: int):
        for n, r in enumerate(self._resultados):
            if r.pagina == i:
                yield r, n == self._activo
