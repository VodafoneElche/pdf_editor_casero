"""Impresión: cada página se dibuja como imagen en la impresora elegida."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QWidget

from .documento import Documento

PPP_MAX = 300


def imprimir(doc: Documento, padre: QWidget, pagina_actual: int = 0) -> bool:
    impresora = QPrinter(QPrinter.PrinterMode.HighResolution)
    impresora.setDocName(doc.titulo)
    impresora.setFromTo(1, doc.num_paginas)
    dialogo = QPrintDialog(impresora, padre)
    dialogo.setWindowTitle("Imprimir")
    dialogo.setOption(QPrintDialog.PrintDialogOption.PrintCurrentPage, True)
    dialogo.setOption(QPrintDialog.PrintDialogOption.PrintPageRange, True)
    if dialogo.exec() != QPrintDialog.DialogCode.Accepted:
        return False

    rango = impresora.printRange()
    if rango == QPrinter.PrintRange.CurrentPage:
        paginas = [pagina_actual]
    elif rango == QPrinter.PrintRange.PageRange:
        paginas = list(range(impresora.fromPage() - 1, impresora.toPage()))
    else:
        paginas = list(range(doc.num_paginas))
    imprimir_paginas(doc, impresora, paginas)
    return True


def imprimir_paginas(doc: Documento, impresora: QPrinter, paginas: list[int]) -> None:
    ppp = min(impresora.resolution(), PPP_MAX)
    p = QPainter(impresora)
    try:
        for k, n in enumerate(paginas):
            if k:
                impresora.newPage()
            datos, an, al, paso = doc.renderizar(n, ppp / 72)
            img = QImage(datos, an, al, paso, QImage.Format.Format_RGB888)
            area = QRectF(impresora.pageLayout().paintRectPixels(impresora.resolution()))
            area.moveTo(0, 0)
            # Encajar la página manteniendo proporción y centrada
            tam = img.size().toSizeF().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
            destino = QRectF(
                area.x() + (area.width() - tam.width()) / 2,
                area.y() + (area.height() - tam.height()) / 2,
                tam.width(),
                tam.height(),
            )
            p.drawImage(destino, img)
    finally:
        p.end()
