"""Impresión con vista previa propia, como en Acrobat.

El cuadro de impresión de Windows 11 no enseña la vista previa en programas como
este («Esta aplicación no admite la vista previa de impresión»), así que usamos
un cuadro propio: impresora, copias, páginas, orientación y, a la derecha, cómo
quedará cada hoja. Cada página se dibuja como imagen en la impresora elegida.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .documento import Documento

PPP_MAX = 300
AUTOMATICA, VERTICAL, HORIZONTAL = range(3)


def leer_rango(texto: str, total: int) -> list[int]:
    """"1-3, 5" → [0, 1, 2, 4] (empezando en 0). Lo que no se entiende o se sale, se ignora."""
    paginas: list[int] = []
    for trozo in texto.replace(";", ",").split(","):
        trozo = trozo.strip()
        if not trozo:
            continue
        desde, _, hasta = trozo.partition("-")
        try:
            a = int(desde) if desde.strip() else 1
            b = int(hasta) if hasta.strip() else (total if _ else a)
        except ValueError:
            continue
        if a > b:
            a, b = b, a
        for n in range(max(a, 1), min(b, total) + 1):
            if n - 1 not in paginas:
                paginas.append(n - 1)
    return paginas


def _girar(img: QImage, hoja: QSize | None, orientacion: int) -> QImage:
    """Con orientación automática, gira 90° la página si así aprovecha mejor la hoja."""
    if orientacion != AUTOMATICA or hoja is None:
        return img
    pagina_apaisada = img.width() > img.height()
    hoja_apaisada = hoja.width() > hoja.height()
    if pagina_apaisada != hoja_apaisada:
        return img.transformed(QTransform().rotate(-90))  # lo de arriba queda a la izquierda
    return img


def _encajar(img: QImage, area: QRectF) -> QRectF:
    tam = img.size().toSizeF().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
    return QRectF(
        area.x() + (area.width() - tam.width()) / 2,
        area.y() + (area.height() - tam.height()) / 2,
        tam.width(),
        tam.height(),
    )


def _imagen(doc: Documento, n: int, ppp: float) -> QImage:
    datos, an, al, paso = doc.renderizar(n, ppp / 72)
    return QImage(datos, an, al, paso, QImage.Format.Format_RGB888).copy()


def imprimir_paginas(doc: Documento, impresora: QPrinter, paginas: list[int], orientacion: int = AUTOMATICA) -> None:
    ppp = min(impresora.resolution(), PPP_MAX)
    p = QPainter(impresora)
    try:
        for k, n in enumerate(paginas):
            if k:
                impresora.newPage()
            area = QRectF(impresora.pageLayout().paintRectPixels(impresora.resolution()))
            area.moveTo(0, 0)
            img = _girar(_imagen(doc, n, ppp), area.size().toSize(), orientacion)
            p.drawImage(_encajar(img, area), img)
    finally:
        p.end()


class DialogoImprimir(QDialog):
    """Elegir impresora y páginas viendo cómo quedará cada hoja."""

    def __init__(self, doc: Documento, padre: QWidget | None, pagina_actual: int = 0):
        super().__init__(padre)
        self.doc, self.pagina_actual = doc, pagina_actual
        self.impresora = QPrinter(QPrinter.PrinterMode.HighResolution)
        self.impresora.setDocName(doc.titulo)
        self.setWindowTitle("Imprimir")
        self._vista_n = 0  # posición dentro de las páginas elegidas

        # --- Opciones (izquierda) ---
        self.lista_impresoras = QComboBox()
        nombres = QPrinterInfo.availablePrinterNames()
        self.lista_impresoras.addItems(nombres)
        defecto = QPrinterInfo.defaultPrinterName()
        if defecto in nombres:
            self.lista_impresoras.setCurrentText(defecto)
        self.lista_impresoras.currentTextChanged.connect(self._cambiar_impresora)

        self.copias = QSpinBox(minimum=1, maximum=99)

        self.todas = QRadioButton(f"Todas ({doc.num_paginas})")
        self.actual = QRadioButton(f"Solo la página actual ({pagina_actual + 1})")
        self.algunas = QRadioButton("Estas páginas:")
        self.rango = QLineEdit(placeholderText="p. ej. 1-3, 5")
        self.todas.setChecked(True)
        grupo = QButtonGroup(self)
        for b in (self.todas, self.actual, self.algunas):
            grupo.addButton(b)
            b.toggled.connect(self._actualizar)
        self.rango.textEdited.connect(lambda _: (self.algunas.setChecked(True), self._actualizar()))
        fila_rango = QHBoxLayout()
        fila_rango.addWidget(self.algunas)
        fila_rango.addWidget(self.rango)
        bloque_paginas = QVBoxLayout()
        for w in (self.todas, self.actual):
            bloque_paginas.addWidget(w)
        bloque_paginas.addLayout(fila_rango)

        self.orientacion = QComboBox()
        self.orientacion.addItems(["Automática (según el documento)", "Vertical", "Horizontal"])
        self.orientacion.currentIndexChanged.connect(self._actualizar)

        mas = QPushButton("Más opciones de la impresora…")
        mas.setToolTip("Doble cara, color, bandeja… con el cuadro de Windows")
        mas.clicked.connect(self._mas_opciones)

        formulario = QFormLayout()
        formulario.addRow("Impresora:", self.lista_impresoras)
        formulario.addRow("Copias:", self.copias)
        formulario.addRow("Páginas:", bloque_paginas)
        formulario.addRow("Orientación:", self.orientacion)
        izquierda = QVBoxLayout()
        izquierda.addLayout(formulario)
        izquierda.addWidget(mas, alignment=Qt.AlignmentFlag.AlignLeft)
        izquierda.addStretch(1)

        # --- Vista previa (derecha) ---
        self.vista = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.vista.setFixedSize(360, 460)
        self.vista.setStyleSheet("background: #d9d9de; border-radius: 6px;")
        self.anterior = QToolButton(text="◀")
        self.siguiente = QToolButton(text="▶")
        self.texto_hoja = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.anterior.clicked.connect(lambda: self._mover(-1))
        self.siguiente.clicked.connect(lambda: self._mover(1))
        navegacion = QHBoxLayout()
        navegacion.addStretch(1)
        for w in (self.anterior, self.texto_hoja, self.siguiente):
            navegacion.addWidget(w)
        navegacion.addStretch(1)
        derecha = QVBoxLayout()
        derecha.addWidget(self.vista)
        derecha.addLayout(navegacion)

        cuerpo = QHBoxLayout()
        cuerpo.addLayout(izquierda, 1)
        cuerpo.addSpacing(16)
        cuerpo.addLayout(derecha)

        botones = QDialogButtonBox()
        self.boton_imprimir = botones.addButton("Imprimir", QDialogButtonBox.ButtonRole.AcceptRole)
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self.boton_imprimir.setDefault(True)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)

        caja = QVBoxLayout(self)
        caja.addLayout(cuerpo)
        caja.addWidget(botones)
        self._cambiar_impresora(self.lista_impresoras.currentText())

    # --- Lo elegido ---
    def paginas(self) -> list[int]:
        if self.actual.isChecked():
            return [self.pagina_actual]
        if self.algunas.isChecked():
            return leer_rango(self.rango.text(), self.doc.num_paginas)
        return list(range(self.doc.num_paginas))

    def orientacion_elegida(self) -> int:
        return self.orientacion.currentIndex()

    def _preparar_impresora(self) -> None:
        o = self.orientacion_elegida()
        if o == AUTOMATICA:
            # El papel según la mayoría de las páginas; las que no encajen se giran
            apaisadas = sum(1 for n in self.paginas() if self.doc.apaisada(n))
            o = HORIZONTAL if apaisadas * 2 > len(self.paginas() or [0]) else VERTICAL
        self.impresora.setPageOrientation(_orientacion_qt(o))
        self.impresora.setCopyCount(self.copias.value())

    def _cambiar_impresora(self, nombre: str) -> None:
        if nombre:
            self.impresora.setPrinterName(nombre)
        self._actualizar()

    def _mas_opciones(self) -> None:
        self._preparar_impresora()
        dialogo = QPrintDialog(self.impresora, self)
        dialogo.setWindowTitle("Más opciones de la impresora")
        if dialogo.exec() == QPrintDialog.DialogCode.Accepted:
            self.copias.setValue(max(1, self.impresora.copyCount()))
            nombre = self.impresora.printerName()
            if nombre and self.lista_impresoras.findText(nombre) < 0:
                self.lista_impresoras.addItem(nombre)
            self.lista_impresoras.blockSignals(True)
            self.lista_impresoras.setCurrentText(nombre)
            self.lista_impresoras.blockSignals(False)
            self._actualizar()

    # --- Vista previa ---
    def _mover(self, paso: int) -> None:
        self._vista_n += paso
        self._actualizar()

    def _actualizar(self, *_):
        self._preparar_impresora()
        paginas = self.paginas()
        self.boton_imprimir.setEnabled(bool(paginas))
        if not paginas:
            self.vista.setPixmap(QPixmap())
            self.vista.setText("Escribe qué páginas\n(por ejemplo 1-3, 5)")
            self.texto_hoja.setText("")
            self.anterior.setEnabled(False)
            self.siguiente.setEnabled(False)
            return
        self._vista_n = max(0, min(self._vista_n, len(paginas) - 1))
        self.texto_hoja.setText(f"Hoja {self._vista_n + 1} de {len(paginas)}")
        self.anterior.setEnabled(self._vista_n > 0)
        self.siguiente.setEnabled(self._vista_n < len(paginas) - 1)
        self.vista.setPixmap(self._dibujar_hoja(paginas[self._vista_n]))

    def _dibujar_hoja(self, n: int) -> QPixmap:
        """La hoja de papel en pequeño, con su margen y la página encajada como saldrá."""
        diseno = self.impresora.pageLayout()
        papel = diseno.fullRectPoints().toRectF()
        util = diseno.paintRectPoints().toRectF()
        caja = QRectF(0, 0, self.vista.width() - 24, self.vista.height() - 24)
        escala = min(caja.width() / papel.width(), caja.height() / papel.height())
        hoja = QPixmap(int(papel.width() * escala) + 2, int(papel.height() * escala) + 2)
        hoja.fill(QColor("white"))
        p = QPainter(hoja)
        try:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            area = QRectF(util.x() * escala, util.y() * escala, util.width() * escala, util.height() * escala)
            img = _girar(_imagen(self.doc, n, 72 * escala * 2), area.size().toSize(), self.orientacion_elegida())
            p.drawImage(_encajar(img, area), img)
            p.setPen(QPen(QColor("#9a9aa2")))
            p.drawRect(0, 0, hoja.width() - 1, hoja.height() - 1)
        finally:
            p.end()
        return hoja


def _orientacion_qt(o: int):
    from PySide6.QtGui import QPageLayout

    return QPageLayout.Orientation.Landscape if o == HORIZONTAL else QPageLayout.Orientation.Portrait


def imprimir(doc: Documento, padre: QWidget, pagina_actual: int = 0) -> bool:
    dialogo = DialogoImprimir(doc, padre, pagina_actual)
    try:
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return False
        paginas = dialogo.paginas()
        if not paginas:
            return False
        dialogo._preparar_impresora()
        imprimir_paginas(doc, dialogo.impresora, paginas, dialogo.orientacion_elegida())
        return True
    finally:
        # Borrar ya la impresora y el cuadro, no al cerrar el programa
        dialogo.impresora = None
        dialogo.deleteLater()
