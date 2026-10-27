"""Comprobación rápida del programa ya empaquetado: `PDFCasero.exe --autoprueba salida.txt`.

La usa GitHub Actions para asegurarse de que el .exe arranca, abre la ventana
y que el OCR funciona con los idiomas incluidos. Escribe el resultado en el
archivo indicado y sale con código 0 si todo va bien.
"""

from __future__ import annotations

import sys
import traceback

import pymupdf

from . import ocr


def _ocr_funciona() -> str:
    tessdata = ocr.buscar_tessdata()
    if tessdata is None:
        raise RuntimeError("No se encuentran los idiomas del OCR")
    # Página con texto convertida en imagen, como si fuera un escaneo
    origen = pymupdf.open()
    origen.new_page().insert_text((72, 100), "Hola mundo desde PDF Casero", fontsize=24)
    foto = origen[0].get_pixmap(dpi=150)
    escaneo = pymupdf.open()
    pagina = escaneo.new_page()
    pagina.insert_image(pagina.rect, pixmap=foto)
    escaneo.new_page().insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=foto)
    # Igual que "Hacer editable": dos páginas a la vez en procesos aparte
    leidas = dict(ocr.reconocer_paginas(escaneo.tobytes(), [0, 1], tessdata, procesos=2))
    textos = [" ".join(p[4] for p in leidas.get(n, [])) for n in (0, 1)]
    for texto in textos:
        if "mundo" not in texto.lower():
            raise RuntimeError(f"El OCR no ha leído bien: {texto!r}")
    return f"OCR ok ({tessdata}), 2 procesos: {textos[0]}"


def ejecutar(salida: str) -> int:
    lineas, codigo = [], 0
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from .ventana import VentanaPrincipal

        app = QApplication.instance() or QApplication(sys.argv)
        ventana = VentanaPrincipal()
        ventana.show()
        QTimer.singleShot(500, app.quit)
        app.exec()
        lineas.append("Ventana ok")
        lineas.append(_ocr_funciona())
    except Exception:
        lineas.append(traceback.format_exc())
        codigo = 1
    with open(salida, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    return codigo
