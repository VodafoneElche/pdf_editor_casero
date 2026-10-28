"""Imprimir con vista previa propia."""

import gc
import os

import pymupdf
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pdfcasero.documento import Documento
from pdfcasero.impresion import AUTOMATICA, HORIZONTAL, DialogoImprimir, imprimir_paginas, leer_rango


def documento(tmp_path):
    origen = pymupdf.open()
    origen.new_page(width=595, height=842).insert_text((72, 80), "Vertical")
    origen.new_page(width=842, height=595).insert_text((72, 80), "Apaisada")
    origen.new_page(width=595, height=842).insert_text((72, 80), "Tercera")
    ruta = tmp_path / "doc.pdf"
    origen.save(ruta)
    return Documento(str(ruta))


@pytest.fixture(autouse=True)
def limpiar():
    # Las impresoras (QPrinter) se borran aquí, mientras sigue viva la aplicación de Qt:
    # si se quedan para el final, Python en Windows se cierra con error tras las pruebas
    yield
    from PySide6.QtWidgets import QApplication

    gc.collect()
    if QApplication.instance():
        QApplication.instance().processEvents()


def cerrar(d):
    d.close()
    d.impresora = None
    d.deleteLater()


def test_leer_rango():
    assert leer_rango("1-3, 5", 10) == [0, 1, 2, 4]
    assert leer_rango("3-1", 10) == [0, 1, 2]
    assert leer_rango("8-", 9) == [7, 8]
    assert leer_rango("0, 12, abc, 2", 5) == [1]
    assert leer_rango("", 5) == []


def test_dialogo_con_vista_previa(tmp_path):
    app = QApplication.instance() or QApplication([])
    d = DialogoImprimir(documento(tmp_path), None, pagina_actual=1)
    assert d.paginas() == [0, 1, 2]
    assert not d.vista.pixmap().isNull()
    assert d.texto_hoja.text() == "Hoja 1 de 3"
    d.actual.setChecked(True)
    assert d.paginas() == [1] and d.texto_hoja.text() == "Hoja 1 de 1"
    d.rango.setText("2-3")
    d.rango.textEdited.emit("2-3")
    assert d.paginas() == [1, 2] and d.algunas.isChecked()
    d.rango.setText("xx")
    d.rango.textEdited.emit("xx")
    assert not d.boton_imprimir.isEnabled()
    cerrar(d)
    app.processEvents()


def test_imprime_a_pdf_girando_las_apaisadas(tmp_path):
    from PySide6.QtPrintSupport import QPrinter

    app = QApplication.instance() or QApplication([])
    doc = documento(tmp_path)
    # Automática con 1 vertical y 1 apaisada → vertical; solo la apaisada → apaisado
    for orientacion, paginas, esperado in ((AUTOMATICA, [0, 1], False), (HORIZONTAL, [0, 1], True), (AUTOMATICA, [1], True)):
        salida = tmp_path / f"impreso{orientacion}{len(paginas)}.pdf"
        impresora = QPrinter(QPrinter.PrinterMode.HighResolution)
        impresora.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        impresora.setOutputFileName(str(salida))
        d = DialogoImprimir(doc, None)
        d.impresora = impresora
        if paginas == [1]:
            d.algunas.setChecked(True)
            d.rango.setText("2")
        d.orientacion.setCurrentIndex(orientacion)
        d._preparar_impresora()
        imprimir_paginas(doc, impresora, paginas, orientacion)
        impreso = pymupdf.open(salida)
        assert len(impreso) == len(paginas)
        assert all((p.rect.width > p.rect.height) == esperado for p in impreso)
        impreso.close()
        cerrar(d)
        del impresora
    app.processEvents()
