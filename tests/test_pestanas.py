"""Varios PDF abiertos a la vez, cada uno en su pestaña."""

import os

import pymupdf
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def ventana(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(QSettings, "value", lambda self, clave, defecto=None, **_: defecto)
    monkeypatch.setattr(QSettings, "setValue", lambda *a, **k: None)
    from pdfcasero.ventana import VentanaPrincipal

    app = QApplication.instance() or QApplication([])
    v = VentanaPrincipal()
    v.show()
    yield v
    for d in v.abiertos:
        d.modificado = False
    v.close()
    app.processEvents()


def pdf(tmp_path, nombre, paginas):
    doc = pymupdf.open()
    for n in range(paginas):
        doc.new_page().insert_text((72, 80), f"{nombre} página {n + 1}")
    ruta = tmp_path / f"{nombre}.pdf"
    doc.save(ruta)
    return str(ruta)


def test_cada_pdf_en_su_pestana(ventana, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    a, b = pdf(tmp_path, "factura", 3), pdf(tmp_path, "carta", 1)
    assert ventana.abrir(a) and ventana.abrir(b)
    assert ventana.pestanas.count() == 2 and ventana.doc.ruta.name == "carta.pdf"
    assert [ventana.pestanas.tabText(i) for i in range(2)] == ["factura.pdf", "carta.pdf"]

    # Volver a la primera: recuerda la página en la que estaba
    ventana.pestanas.setCurrentIndex(0)
    assert ventana.doc.ruta.name == "factura.pdf" and ventana.doc.num_paginas == 3
    ventana.visor.ir_a_pagina(2)
    ventana.pestanas.setCurrentIndex(1)
    assert ventana.etiqueta_total.text().strip() == "de 1"
    ventana.pestanas.setCurrentIndex(0)
    assert ventana.doc.vista[0] == 2

    # Abrir otra vez el mismo PDF no duplica la pestaña
    assert ventana.abrir(a)
    assert ventana.pestanas.count() == 2 and ventana.pestanas.currentIndex() == 0

    # Un cambio sin guardar se ve en la pestaña y pregunta al cerrar
    ventana.doc.modificado = True
    ventana._actualizar_estado()
    assert ventana.pestanas.tabText(0) == "● factura.pdf"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    assert not ventana.cerrar_pestana(0) and ventana.pestanas.count() == 2
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard)
    assert ventana.cerrar_pestana(0)
    assert ventana.pestanas.count() == 1 and ventana.doc.ruta.name == "carta.pdf"

    # Cerrar la última vuelve a la pantalla de bienvenida
    assert ventana.cerrar_documento()
    assert ventana.doc is None and ventana.pila.currentIndex() == 0
