"""Arranque: python -m pdfcasero [archivo.pdf]"""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .estilo import HOJA_ESTILO
from .ventana import VentanaPrincipal


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Casero")
    app.setOrganizationName("PDFCasero")
    if sys.platform != "win32":
        app.setStyle("Fusion")  # en Windows se usa el estilo nativo
    app.setStyleSheet(HOJA_ESTILO)
    app.setWindowIcon(QIcon.fromTheme(QIcon.ThemeIcon.DocumentOpen))
    ventana = VentanaPrincipal()
    ventana.show()
    # "Abrir con" desde el Explorador de Windows pasa la ruta como argumento
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".pdf"):
            ventana.abrir(arg)
            break
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
