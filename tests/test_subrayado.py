"""Subrayador fosforescente: marcas de color que se guardan dentro del PDF."""

import os

import pymupdf
import pytest

from pdfcasero.documento import Documento
from pdfcasero.subrayado import COLOR

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def apuntes(tmp_path):
    ruta = tmp_path / "apuntes.pdf"
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 100), "La fotosintesis ocurre en las hojas", fontsize=12)
    p.insert_text((72, 120), "y produce oxigeno para todos", fontsize=12)
    doc.save(ruta)
    return ruta


def palabras_de(d, *textos):
    return [w[:4] for w in d.palabras(0) if w[4] in textos]


def test_subrayar_se_guarda_como_resaltado_real(apuntes, tmp_path):
    d = Documento(apuntes)
    d.subrayar(0, palabras_de(d, "fotosintesis", "ocurre", "oxigeno"), COLOR["rosa"])
    destino = d.guardar(tmp_path / "subrayado.pdf")

    doc = pymupdf.open(destino)
    pagina = doc[0]
    marcas = list(pagina.annots())
    assert len(marcas) == 1 and marcas[0].type[1] == "Highlight"
    assert marcas[0].colors["stroke"] == pytest.approx(COLOR["rosa"], abs=0.01)
    # Las dos palabras de la primera línea van en una sola franja; la otra línea, aparte
    assert len(marcas[0].vertices) == 8
    texto = pagina.get_textbox(marcas[0].rect)
    assert "fotosintesis" in texto and "oxigeno" in texto


def test_una_linea_entera_queda_marcada_hasta_el_final(apuntes):
    """Al arrastrar por toda una línea se marcan todas sus palabras, no solo la primera."""
    d = Documento(apuntes)
    linea = [w for w in d.palabras(0) if w[1] < 105]
    d.subrayar(0, [w[:4] for w in linea], COLOR["amarillo"])
    (_, franjas), = d.subrayados(0)
    assert len(franjas) == 1
    assert franjas[0].x0 <= linea[0][0] + 0.5 and franjas[0].x1 >= linea[-1][2] - 0.5


def test_cada_color_y_quitar(apuntes):
    d = Documento(apuntes)
    for clave in ("amarillo", "verde", "rojo"):
        d.subrayar(0, palabras_de(d, "hojas"), COLOR[clave])
    assert len(d.subrayados(0)) == 3
    x0, y0, x1, y1 = palabras_de(d, "hojas")[0]
    xref = d.subrayado_en(0, (x0 + x1) / 2, (y0 + y1) / 2)
    assert xref == d.subrayados(0)[-1][0]  # el de encima
    d.quitar_subrayado(0, xref)
    assert len(d.subrayados(0)) == 2
    assert d.subrayado_en(0, 10, 10) is None
    d.deshacer()
    assert len(d.subrayados(0)) == 3


@pytest.fixture
def ventana(monkeypatch):
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


def test_arrastrar_con_el_rotulador(ventana, apuntes):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    assert ventana.abrir(str(apuntes))
    ventana.acc_subrayar.trigger()
    assert ventana.visor.modo == "subrayar" and ventana.barra_subrayado.isVisible()
    ventana._acciones_subrayado["verde"].trigger()

    pagina = ventana.visor._paginas[0]
    e = ventana.visor.escala
    x0, y0, x1, y1 = palabras_de(ventana.doc, "ocurre")[0]
    medio_y = round((y0 + y1) / 2 * e)
    QTest.mousePress(pagina, Qt.MouseButton.LeftButton, pos=QPoint(round((x0 + 1) * e), medio_y))
    QTest.mouseMove(pagina, QPoint(round((x1 - 1) * e), medio_y))
    QTest.mouseRelease(pagina, Qt.MouseButton.LeftButton, pos=QPoint(round((x1 - 1) * e), medio_y))

    marcas = ventana.doc.subrayados(0)
    assert len(marcas) == 1 and ventana.doc.modificado
    assert "ocurre" in ventana.doc._doc[0].get_textbox(marcas[0][1][0]).strip()

    # Doble clic marca una palabra entera
    x0, y0, x1, y1 = palabras_de(ventana.doc, "oxigeno")[0]
    QTest.mouseDClick(pagina, Qt.MouseButton.LeftButton, pos=QPoint(round((x0 + x1) / 2 * e), round((y0 + y1) / 2 * e)))
    assert len(ventana.doc.subrayados(0)) == 2

    # Goma: clic encima quita la marca
    ventana._acciones_subrayado[None].trigger()
    QTest.mouseClick(pagina, Qt.MouseButton.LeftButton, pos=QPoint(round((x0 + x1) / 2 * e), round((y0 + y1) / 2 * e)))
    assert len(ventana.doc.subrayados(0)) == 1


def test_ctrl_u_con_texto_seleccionado_subraya_al_momento(ventana, apuntes):
    assert ventana.abrir(str(apuntes))
    ventana.visor.seleccionar_pagina()
    ventana.acc_subrayar.trigger()
    assert ventana.visor.modo == "leer" and not ventana.acc_subrayar.isChecked()
    assert len(ventana.doc.subrayados(0)) == 1
