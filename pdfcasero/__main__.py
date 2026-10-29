"""Arranque: python -m pdfcasero [archivo.pdf]"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from PySide6.QtCore import QSettings

from . import estilo
from .ventana import VentanaPrincipal


ICONO = Path(__file__).resolve().parent / "recursos" / "icono.png"


def traducir(app: QApplication) -> None:
    """Los botones y avisos que trae Qt (Guardar, Descartar, Cancelar, Sí, No…) en español."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    QLocale.setDefault(QLocale(QLocale.Language.Spanish, QLocale.Country.Spain))
    carpeta = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    traductor = QTranslator(app)
    if traductor.load("qtbase_es", carpeta):
        app.installTranslator(traductor)
        app._traductor = traductor  # que no se borre


def preparar_aspecto(app: QApplication) -> None:
    """Los colores elegidos en la app, sin hacer caso del modo oscuro de Windows.

    Con el modo oscuro de Windows, el texto salía en blanco y los cuadros
    (página, buscar, zoom) se quedaban en blanco sobre blanco. El modo oscuro
    se elige dentro de la app («Oscuro» en los colores de la pantalla de inicio).
    """
    app.setStyle("Fusion")
    ajustes = QSettings("PDFCasero", "PDFCasero")
    estilo.aplicar(app, ajustes.value("tema", "gris"), ajustes.value("barra", None))


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--autoprueba":
        from .autoprueba import ejecutar

        return ejecutar(sys.argv[2])
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Familiar")
    app.setOrganizationName("PDFCasero")
    traducir(app)
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
