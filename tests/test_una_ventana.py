"""Los PDF que se abren con la app ya abierta van a sus pestañas; una pestaña se puede sacar."""

import os
import time

import pymupdf
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def app(monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(QSettings, "value", lambda self, clave, defecto=None, **_: defecto)
    monkeypatch.setattr(QSettings, "setValue", lambda *a, **k: None)
    return QApplication.instance() or QApplication([])


def pdf(tmp_path, nombre):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 80), nombre)
    ruta = tmp_path / f"{nombre}.pdf"
    doc.save(ruta)
    return str(ruta)


def esperar(app, condicion, segundos=5):
    limite = time.time() + segundos
    while not condicion() and time.time() < limite:
        app.processEvents()
        time.sleep(0.02)
    return condicion()


def test_abrir_con_la_app_ya_abierta(app, tmp_path):
    from pdfcasero.__main__ import enviar_a_la_abierta, escuchar
    from pdfcasero.ventana import VentanaPrincipal

    nombre = f"PDFFamiliar-prueba-{time.time_ns()}"
    assert not enviar_a_la_abierta([pdf(tmp_path, "nadie")], nombre)  # no hay ninguna abierta
    servidor = escuchar(app, nombre)
    v = VentanaPrincipal()
    v.show()
    try:
        assert enviar_a_la_abierta([pdf(tmp_path, "uno"), pdf(tmp_path, "dos")], nombre)
        assert esperar(app, lambda: len(v.abiertos) == 2)
        assert [d.ruta.name for d in v.abiertos] == ["uno.pdf", "dos.pdf"]
    finally:
        v.close()
        servidor.close()
        app.processEvents()


def test_sacar_una_pestana_a_otra_ventana(app, tmp_path):
    from PySide6.QtCore import QPoint

    from pdfcasero import ventana as modulo

    v = modulo.VentanaPrincipal()
    v.show()
    for n in ("a", "b", "c"):
        v.abrir(pdf(tmp_path, n))
    v.visor.ir_a_pagina(0)
    nueva = v.sacar_pestana(1, QPoint(300, 300))
    try:
        assert [d.ruta.name for d in v.abiertos] == ["a.pdf", "c.pdf"]
        assert [d.ruta.name for d in nueva.abiertos] == ["b.pdf"]
        assert nueva.doc.ruta.name == "b.pdf" and nueva.isVisible()
        assert v.pestanas.count() == 2 and nueva.pestanas.count() == 1
        # Con una sola pestaña no se saca (sería la misma ventana)
        assert nueva.sacar_pestana(0) is None
        # Los PDF que lleguen de fuera van a la última ventana usada
        assert modulo.ventana_activa() in (v, nueva)
    finally:
        for w in (nueva, v):
            w.close()
        app.processEvents()
    assert nueva not in modulo.VENTANAS and v not in modulo.VENTANAS


def test_arrastrar_la_pestana_fuera(app, tmp_path):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from pdfcasero import ventana as modulo

    v = modulo.VentanaPrincipal()
    v.show()
    for n in ("a", "b"):
        v.abrir(pdf(tmp_path, n))
    barra = v.pestanas
    sacadas = []
    barra.sacar.connect(lambda i, p: sacadas.append(i))
    barra.sacar.disconnect(v.sacar_pestana)  # solo comprobar el gesto
    centro = QPointF(barra.tabRect(0).center())

    def evento(tipo, pos, botones):
        return QMouseEvent(tipo, pos, barra.mapToGlobal(pos), Qt.MouseButton.LeftButton, botones, Qt.KeyboardModifier.NoModifier)

    QApplication.sendEvent(barra, evento(QMouseEvent.Type.MouseButtonPress, centro, Qt.MouseButton.LeftButton))
    QApplication.sendEvent(barra, evento(QMouseEvent.Type.MouseMove, centro + QPointF(5, 10), Qt.MouseButton.LeftButton))
    assert sacadas == []  # un poco no basta
    QApplication.sendEvent(barra, evento(QMouseEvent.Type.MouseMove, centro + QPointF(10, 150), Qt.MouseButton.LeftButton))
    assert sacadas == [0]
    for d in v.abiertos:
        d.modificado = False
    v.close()
    app.processEvents()
