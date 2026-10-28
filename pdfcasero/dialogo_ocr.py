"""Hacer editable: pasa el OCR en segundo plano sin congelar la ventana."""

from __future__ import annotations

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
        # El trabajo de verdad se hace en otros procesos: este hilo solo espera y avisa
        try:
            total = len(self.paginas)
            self.avance.emit(0, total)
            resultados = ocr.reconocer_paginas(
                self.datos_pdf, self.paginas, self.tessdata, cancelado=lambda: self.cancelado
            )
            try:
                for k, (n, palabras) in enumerate(resultados, start=1):
                    if self.cancelado:
                        break
                    self.paginaLista.emit(n, palabras)
                    self.avance.emit(k, total)
            finally:
                resultados.close()  # para los procesos aunque se cancele a medias
        except Exception as e:  # el aviso lo muestra la ventana
            self.fallo.emit(str(e) or type(e).__name__)


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
    caja = QMessageBox(padre)
    caja.setIcon(QMessageBox.Icon.Information)
    caja.setWindowTitle("Ya es editable")
    caja.setText("Este PDF ya es editable.")
    caja.setInformativeText(
        "Todas sus páginas tienen texto de verdad: se puede buscar, copiar y cambiar con «Editar texto». "
        "No hace falta «Hacer editable».\n\n"
        f"Reconocerlo igualmente tardaría varios minutos ({doc.num_paginas} páginas) y puede duplicar el texto."
    )
    entendido = caja.addButton("Entendido", QMessageBox.ButtonRole.AcceptRole)
    igualmente = caja.addButton("Reconocer igualmente", QMessageBox.ButtonRole.DestructiveRole)
    caja.setDefaultButton(entendido)
    caja.exec()
    return list(range(doc.num_paginas)) if caja.clickedButton() is igualmente else None
