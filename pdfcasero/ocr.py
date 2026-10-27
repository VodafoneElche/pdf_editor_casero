"""OCR con el motor Tesseract que ya trae PyMuPDF.

No hace falta instalar Tesseract aparte: solo los archivos de idioma
(`spa.traineddata` y `eng.traineddata`), que se descargan una vez (unos 6 MB).
"""

from __future__ import annotations

import os
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

import pymupdf

IDIOMAS = ("spa", "eng")
URL_IDIOMA = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{}.traineddata"
DPI_OCR = 300

Palabra = tuple[float, float, float, float, str]  # x0, y0, x1, y1, texto (en puntos PDF)


def carpeta_usuario() -> Path:
    """Carpeta donde se guardan los idiomas descargados."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), ".local", "share")
    return Path(base) / "PDFCasero" / "tessdata"


def _candidatas() -> list[Path]:
    rutas = []
    if os.environ.get("TESSDATA_PREFIX"):
        rutas.append(Path(os.environ["TESSDATA_PREFIX"]))
    # Junto al programa (el instalador los incluirá aquí)
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    rutas.append(base / "tessdata")
    rutas.append(carpeta_usuario())
    # Tesseract instalado en el sistema
    rutas.append(Path(r"C:\Program Files\Tesseract-OCR\tessdata"))
    rutas += sorted(Path("/usr/share/tesseract-ocr").glob("*/tessdata"), reverse=True)
    rutas.append(Path("/usr/share/tessdata"))
    return rutas


def buscar_tessdata(idiomas=IDIOMAS) -> Path | None:
    """Primera carpeta que tenga todos los idiomas necesarios, o None."""
    for ruta in _candidatas():
        if all((ruta / f"{i}.traineddata").is_file() for i in idiomas):
            return ruta
    return None


def descargar_idiomas(
    destino: Path | None = None,
    idiomas=IDIOMAS,
    progreso: Callable[[int, int], bool] | None = None,
) -> Path:
    """Descarga los idiomas que falten. `progreso(bytes, total)` devuelve False para cancelar."""
    destino = destino or carpeta_usuario()
    destino.mkdir(parents=True, exist_ok=True)
    for idioma in idiomas:
        final = destino / f"{idioma}.traineddata"
        if final.is_file():
            continue
        parcial = final.with_suffix(".parcial")
        cancelado = False
        with urllib.request.urlopen(URL_IDIOMA.format(idioma), timeout=30) as r, open(parcial, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            leido = 0
            while bloque := r.read(64 * 1024):
                f.write(bloque)
                leido += len(bloque)
                if progreso and progreso(leido, total) is False:
                    cancelado = True
                    break
        if cancelado:
            parcial.unlink(missing_ok=True)
            raise InterruptedError("Descarga cancelada")
        parcial.replace(final)
    return destino


def reconocer_pagina(pagina: pymupdf.Page, tessdata: Path, idiomas=IDIOMAS, dpi: int = DPI_OCR) -> list[Palabra]:
    """Pasa el OCR a una página y devuelve sus palabras con su posición."""
    tp = pagina.get_textpage_ocr(dpi=dpi, full=True, language="+".join(idiomas), tessdata=str(tessdata))
    return [(w[0], w[1], w[2], w[3], w[4]) for w in pagina.get_text("words", textpage=tp, sort=True) if w[4].strip()]


def insertar_capa_texto(pagina: pymupdf.Page, palabras: list[Palabra]) -> None:
    """Añade el texto reconocido como capa invisible encima de la imagen.

    La página se ve igual que antes, pero el texto ya se puede buscar,
    seleccionar y copiar.
    """
    if not palabras:
        return
    from .edicion import preparar

    preparar(pagina)
    fuente = pymupdf.Font("helv")
    escritor = pymupdf.TextWriter(pagina.rect)
    for x0, y0, x1, y1, texto in palabras:
        ancho_1pt = fuente.text_length(texto, fontsize=1)
        alto = y1 - y0
        if ancho_1pt <= 0 or alto <= 0:
            continue
        # Tamaño de letra que ocupa el ancho de la palabra, sin pasarse mucho de su alto
        tam = min((x1 - x0) / ancho_1pt, alto * 1.2)
        escritor.append(pymupdf.Point(x0, y1 - alto * 0.2), texto, font=fuente, fontsize=tam)
    # PyMuPDF ya tiene en cuenta si la página está girada. render_mode=3 = texto invisible
    escritor.write_text(pagina, render_mode=3)
