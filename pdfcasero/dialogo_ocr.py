"""Hacer editable: pasa el OCR en segundo plano sin congelar la ventana."""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget

from . import ocr
from .documento import Documento


class HiloOCR(QThread):
    """Reconoce las páginas en una copia del PDF; la ventana aplica el resultado."""

    paginaLista = Signal(int, list)  # número de página, palabras
    avance = Signal(int, int)  # hechas, total
    fallo = Signal(str)

    def __init__(self, datos_pdf: bytes, paginas: list[int], tessdata):
        super().__init__()
        self.datos_pdf = datos_pdf
        self.paginas = paginas
        self.tessdata = tessdata
        self.cancelado = False

    def run(self):
        try:
            doc = pymupdf.open(stream=self.datos_pdf, filetype="pdf")
            for k, n in enumerate(self.paginas):
                if self.cancelado:
                    break
                self.avance.emit(k, len(self.paginas))
                self.paginaLista.emit(n, ocr.reconocer_pagina(doc[n], self.tessdata))
            doc.close()
        except Exception as e:  # el aviso lo muestra la ventana
            self.fallo.emit(str(e))


def asegurar_idiomas(padre: QWidget):
    """Devuelve la carpeta de idiomas; si faltan, ofrece descargarlos (unos 6 MB)."""
    ruta = ocr.buscar_tessdata()
    if ruta:
        return ruta
    r = QMessageBox.question(
        padre,
        "Descargar idiomas",
        "Para reconocer el texto hacen falta los idiomas español e inglés (unos 6 MB).\n\n"
        "Solo se descargan una vez. ¿Descargarlos ahora?",
    )
    if r != QMessageBox.StandardButton.Yes:
        return None
    dialogo = QProgressDialog("Descargando idiomas…", "Cancelar", 0, 100, padre)
    dialogo.setWindowTitle("Descargando")
    dialogo.setMinimumDuration(0)

    def progreso(leido, total):
        if total:
            dialogo.setValue(int(leido * 100 / total))
        QApplication.processEvents()
        return not dialogo.wasCanceled()

    try:
        ruta = ocr.descargar_idiomas(progreso=progreso)
    except InterruptedError:
        return None
    except Exception as e:
        QMessageBox.critical(
            padre, "Sin conexión", f"No se pudieron descargar los idiomas. Comprueba la conexión a internet.\n\n{e}"
        )
        return None
    finally:
        dialogo.close()
    return ruta


def elegir_paginas(padre: QWidget, doc: Documento) -> list[int] | None:
    """Páginas a reconocer: las que no tienen texto, o todas si el usuario lo pide."""
    sin_texto = doc.paginas_sin_texto()
    if sin_texto:
        return sin_texto
    r = QMessageBox.question(
        padre,
        "Ya tiene texto",
        "Todas las páginas de este PDF ya tienen texto que se puede buscar y copiar.\n\n"
        "¿Quieres pasar el reconocimiento igualmente? Puede duplicar el texto.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return list(range(doc.num_paginas)) if r == QMessageBox.StandardButton.Yes else None
