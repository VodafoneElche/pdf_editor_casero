"""Arranque: python -m pdfcasero [archivo.pdf]"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .estilo import HOJA_ESTILO
from .ventana import VentanaPrincipal


ICONO = Path(__file__).resolve().parent / "recursos" / "icono.png"


def preparar_aspecto(app: QApplication) -> None:
    """Siempre en claro, también si Windows está en modo oscuro.

    Con el modo oscuro, Windows pintaba el texto en blanco y los cuadros
    (página, buscar, zoom) se quedaban en blanco sobre blanco.
    """
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:  # Qt anterior a 6.8
        pass
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())
    app.setStyleSheet(HOJA_ESTILO)


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--autoprueba":
        from .autoprueba import ejecutar

        return ejecutar(sys.argv[2])
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Casero")
    app.setOrganizationName("PDFCasero")
    preparar_aspecto(app)
    app.setWindowIcon(QIcon(str(ICONO)))
    ventana = VentanaPrincipal()
    ventana.show()
    # "Abrir con" desde el Explorador de Windows pasa la ruta como argumento
    for arg in sys.argv[1:]:
        if arg.lower().endswith((".pdf", ".docx")):
            ventana.abrir(arg)  # cada uno en su pestaña
    return app.exec()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
