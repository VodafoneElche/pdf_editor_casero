"""Desplazamiento suave con la rueda del ratón y el touchpad.

Qt mueve la barra a saltos fijos de `singleStep` píxeles. Con un touchpad de
Windows, que manda muchos movimientos pequeños, eso se nota como tirones; con
una rueda, como saltos secos de una línea entera. Aquí cada movimiento se
convierte en píxeles exactos y la barra se acerca al destino poco a poco,
fotograma a fotograma, en vez de saltar.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QScrollBar

# Píxeles que avanza una "línea" de rueda (Windows usa 3 líneas por muesca)
PIXELES_POR_LINEA = 36
# Parte del camino que se recorre en cada fotograma (~60 por segundo)
FRACCION_POR_FOTOGRAMA = 0.35
FOTOGRAMA_MS = 16


class DesplazamientoSuave(QObject):
    """Lleva una barra de desplazamiento hacia un destino sin saltos."""

    def __init__(self, barra: QScrollBar):
        super().__init__(barra)
        self.barra = barra
        self._pos = float(barra.value())
        self._destino = self._pos
        self._ultimo = barra.value()
        self._reloj = QTimer(self, interval=FOTOGRAMA_MS)
        self._reloj.timeout.connect(self._paso)

    @property
    def activo(self) -> bool:
        return self._reloj.isActive()

    @staticmethod
    def pixeles(delta_angulo: int, delta_pixeles: int) -> float:
        """Píxeles a mover. Si el sistema da píxeles exactos, se usan tal cual;
        si no, se convierte el giro (120 = una muesca) a píxeles sin redondear."""
        if delta_pixeles:
            return float(delta_pixeles)
        lineas = QApplication.wheelScrollLines() if QApplication.instance() else 3
        return delta_angulo / 120 * max(1, lineas) * PIXELES_POR_LINEA

    def mover(self, pixeles: float) -> None:
        """Pixeles > 0 sube (como la rueda hacia delante)."""
        if not self.activo or self.barra.value() != self._ultimo:
            # Empieza de nuevo desde donde esté la barra (pudo moverla otra cosa)
            self._pos = self._destino = float(self.barra.value())
            self._ultimo = self.barra.value()
        self._destino = max(self.barra.minimum(), min(self.barra.maximum(), self._destino - pixeles))
        if abs(self._destino - self._pos) >= 0.5:
            if not self.activo:
                self._reloj.start()
            self._paso()

    def parar(self) -> None:
        self._reloj.stop()

    def _paso(self) -> None:
        if self.barra.value() != self._ultimo:
            # Alguien movió la barra a mano (arrastre, ir a página…): se respeta
            self.parar()
            return
        resto = self._destino - self._pos
        if abs(resto) < 0.5:
            self._pos = self._destino
            self.parar()
        else:
            avance = resto * FRACCION_POR_FOTOGRAMA
            # Al final, al menos medio píxel por fotograma para no quedarse arrastrando
            if abs(avance) < 0.5:
                avance = 0.5 if resto > 0 else -0.5
            self._pos += avance
        self.barra.setValue(round(self._pos))
        self._ultimo = self.barra.value()
