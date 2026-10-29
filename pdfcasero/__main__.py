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


def _nombre_servidor() -> str:
    import getpass

    try:
        usuario = getpass.getuser()
    except Exception:
        usuario = "usuario"
    return f"PDFFamiliar-{usuario}"


def enviar_a_la_abierta(rutas: list[str], nombre: str | None = None) -> bool:
    """Si PDF Familiar ya está abierto, le pasa los PDF para que los abra en sus pestañas.

    Devuelve True si había uno abierto (y entonces este se cierra sin abrir otra ventana).
    """
    import json

    from PySide6.QtNetwork import QLocalSocket

    conexion = QLocalSocket()
    conexion.connectToServer(nombre or _nombre_servidor())
    if not conexion.waitForConnected(500):
        return False
    if sys.platform == "win32":
        try:  # deja que la ventana abierta se ponga delante
            import ctypes

            ctypes.windll.user32.AllowSetForegroundWindow(-1)
        except Exception:
            pass
    conexion.write(json.dumps(rutas).encode("utf-8"))
    conexion.flush()
    conexion.waitForBytesWritten(2000)
    conexion.disconnectFromServer()
    if conexion.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        conexion.waitForDisconnected(1000)
    return True


def escuchar(app: QApplication, nombre: str | None = None):
    """Recibe los PDF que se abren con la app ya abierta y los pone en la última ventana usada."""
    import json

    from PySide6.QtNetwork import QLocalServer

    nombre = nombre or _nombre_servidor()
    servidor = QLocalServer(app)
    QLocalServer.removeServer(nombre)  # por si quedó uno de una vez que se cerró mal
    servidor.listen(nombre)

    def nueva_conexion():
        conexion = servidor.nextPendingConnection()
        datos = bytearray()

        def leer():
            datos.extend(bytes(conexion.readAll()))

        def terminar():
            leer()
            conexion.deleteLater()
            try:
                rutas = json.loads(datos.decode("utf-8") or "[]")
            except ValueError:
                return
            from .ventana import ventana_activa

            ventana = ventana_activa()
            if ventana is None:
                return
            ventana.traer_al_frente()
            for ruta in rutas:
                ventana.abrir(ruta)

        conexion.readyRead.connect(leer)
        conexion.disconnected.connect(terminar)

    servidor.newConnection.connect(nueva_conexion)
    return servidor


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--autoprueba":
        from .autoprueba import ejecutar

        return ejecutar(sys.argv[2])
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Familiar")
    app.setOrganizationName("PDFCasero")
    traducir(app)
    preparar_aspecto(app)
    # "Abrir con" desde el Explorador de Windows pasa la ruta como argumento
    rutas = [str(Path(a).resolve()) for a in sys.argv[1:] if a.lower().endswith((".pdf", ".docx"))]
    # Si ya hay un PDF Familiar abierto, los PDF van a sus pestañas y no se abre otra ventana
    if enviar_a_la_abierta(rutas):
        return 0
    app._servidor = escuchar(app)
    app.setWindowIcon(QIcon(str(ICONO)))
    ventana = VentanaPrincipal()
    ventana.show()
    for ruta in rutas:
        ventana.abrir(ruta)  # cada uno en su pestaña
    return app.exec()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
