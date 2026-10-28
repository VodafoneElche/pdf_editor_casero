"""OCR con el motor Tesseract que ya trae PyMuPDF.

No hace falta instalar Tesseract aparte: solo los archivos de idioma
(`spa.traineddata` y `eng.traineddata`), que se descargan una vez (unos 6 MB).
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
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


# --- Varias páginas a la vez, en procesos aparte -------------------------------
# PyMuPDF no suelta el "candado" de Python mientras hace el OCR, así que en un
# hilo normal congelaba la ventana. En procesos aparte la ventana sigue viva y,
# además, se reconocen varias páginas a la vez (una por núcleo del procesador).
_doc_del_proceso = None


def _iniciar_proceso(datos_pdf: bytes) -> None:
    global _doc_del_proceso
    _doc_del_proceso = pymupdf.open(stream=datos_pdf, filetype="pdf")


def _reconocer_en_proceso(n: int, tessdata: str) -> tuple[int, list[Palabra]]:
    return n, reconocer_pagina(_doc_del_proceso[n], Path(tessdata))


def procesos_recomendados() -> int:
    """Uno por núcleo, dejando uno libre para la ventana, y como mucho 4 (cada uno usa memoria)."""
    return max(1, min(4, (os.cpu_count() or 2) - 1))


def reconocer_paginas(
    datos_pdf: bytes,
    paginas: list[int],
    tessdata: Path,
    procesos: int | None = None,
    cancelado: Callable[[], bool] = lambda: False,
) -> Iterator[tuple[int, list[Palabra]]]:
    """Reconoce esas páginas en paralelo y va devolviendo (página, palabras) según terminan."""
    procesos = min(procesos or procesos_recomendados(), len(paginas)) or 1
    pool = ProcessPoolExecutor(
        max_workers=procesos,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_iniciar_proceso,
        initargs=(datos_pdf,),
    )
    try:
        pendientes = {pool.submit(_reconocer_en_proceso, n, str(tessdata)) for n in paginas}
        while pendientes:
            hechas, pendientes = wait(pendientes, timeout=0.3, return_when=FIRST_COMPLETED)
            for futuro in hechas:
                yield futuro.result()
            if cancelado():
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


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
