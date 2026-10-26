# Receta de PyInstaller: convierte PDF Casero en una carpeta con PDFCasero.exe.
# Uso (desde la raíz del repositorio):  pyinstaller packaging/pdfcasero.spec
# Antes hay que descargar los idiomas del OCR en packaging/tessdata (ver README).
import os
from pathlib import Path

RAIZ = Path(SPECPATH).parent
TESSDATA = RAIZ / "packaging" / "tessdata"
idiomas = [(str(p), "tessdata") for p in TESSDATA.glob("*.traineddata")]
if not idiomas:
    raise SystemExit("Faltan los idiomas del OCR en packaging/tessdata")

# Partes de Qt que no usamos: así el instalador pesa bastante menos
NO_USADOS = [
    "tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtMultimedia",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtBluetooth", "PySide6.QtPositioning",
    # Extras opcionales de PyMuPDF (tablas a pandas, IA de maquetación…) que no usamos
    "numpy", "pandas", "onnxruntime", "PIL", "lxml", "yaml", "matplotlib", "scipy",
]
# Bibliotecas y plugins de Qt que arrastra PySide6 sin hacer falta
SOBRAN = ("qt6qml", "qt6quick", "virtualkeyboard", "qt6pdf", "qt6network", "qt6svg", "qt6opengl",
          "opengl32sw", "qtvirtualkeyboard", "/qml/", "\\qml\\", "tls", "networkinformation")


def sobra(ruta: str) -> bool:
    r = ruta.lower().replace("\\", "/")
    if "translations/" in r and not any(i in r for i in ("_es.qm", "_en.qm")):
        return True
    return any(x in r for x in SOBRAN)


a = Analysis(
    [str(RAIZ / "lanzar.pyw")],
    pathex=[str(RAIZ)],
    datas=[(str(RAIZ / "pdfcasero" / "recursos"), "pdfcasero/recursos"), *idiomas],
    excludes=NO_USADOS,
    noarchive=False,
)
a.binaries = [b for b in a.binaries if not sobra(b[0]) and not sobra(b[1])]
a.datas = [d for d in a.datas if not sobra(d[0])]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDFCasero",
    icon=str(RAIZ / "packaging" / "icono.ico"),
    console=False,
    upx=False,
    version=str(RAIZ / "packaging" / "version.txt") if os.name == "nt" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PDFCasero", upx=False)
