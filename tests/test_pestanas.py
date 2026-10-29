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


def test_inicio_colores_y_recientes(ventana, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    guardado = {}
    monkeypatch.setattr(type(ventana.ajustes), "setValue", lambda self, k, v: guardado.__setitem__(k, v))
    monkeypatch.setattr(type(ventana.ajustes), "value", lambda self, k, d=None, **_: guardado.get(k, d))
    hoja = lambda: QApplication.instance().styleSheet()  # noqa: E731
    # Los botones de color cambian el fondo de toda la app y se recuerdan; la barra lo sigue
    assert set(ventana.bienvenida.muestras) == {"gris", "rosa", "rojo", "naranja", "celeste", "oscuro"}
    ventana.bienvenida.muestras["celeste"].click()
    assert guardado["tema"] == "celeste" and "#e6f2fb" in hoja() and "#bcdcf3" in hoja()
    assert ventana.bienvenida.muestras_barra["celeste"].isChecked()
    # La barra de menú se puede elegir aparte: fondo celeste con barra rosa
    ventana.bienvenida.muestras_barra["rosa"].click()
    assert guardado["barra"] == "rosa" and "#e6f2fb" in hoja() and "#f5c9dc" in hoja() and "#bcdcf3" not in hoja()
    ventana.bienvenida.muestras["gris"].click()
    assert "#f5f5f7" in hoja() and "#f5c9dc" in hoja()
    ventana.bienvenida.muestras_barra["gris"].click()
    assert "#f5c9dc" not in hoja()

    # Un clic en un reciente lo abre
    ruta = pdf(tmp_path, "reciente", 1)
    ventana.bienvenida.actualizar([ruta])
    lista = ventana.bienvenida.lista
    lista.itemClicked.emit(lista.item(0))
    assert ventana.doc is not None and ventana.doc.ruta.name == "reciente.pdf"


def test_proteger_con_contrasena(ventana, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from pdfcasero import ventana as modulo
    from pdfcasero.documento import ContrasenaNecesaria, Documento

    ruta = pdf(tmp_path, "privado", 2)
    assert ventana.abrir(ruta)
    assert ventana.acc_proteger.isEnabled()
    monkeypatch.setattr(modulo.DialogoContrasena, "pedir", classmethod(lambda cls, padre: "clave1234"))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    ventana.proteger_con_contrasena()
    # El archivo ya pide la contraseña, y con ella se abre y se lee
    assert pymupdf.open(ruta).needs_pass
    with pytest.raises(ContrasenaNecesaria):
        Documento(ruta)
    assert Documento(ruta, "clave1234").num_paginas == 2
    # La app sigue con el PDF abierto y sabe que está protegido
    assert ventana.doc.protegido and ventana.doc.num_paginas == 2
    # Lo que se envía a Google o a Word va sin contraseña
    assert not pymupdf.open(stream=ventana.doc.copia_en_memoria(), filetype="pdf").needs_pass
    # Y se puede quitar
    ventana.doc.poner_contrasena(None)
    ventana.guardar()
    assert not pymupdf.open(ruta).needs_pass and not ventana.doc.protegido


def test_dialogo_contrasena_comprueba_las_dos(ventana):
    from pdfcasero.ventana import DialogoContrasena

    d = DialogoContrasena(ventana)
    d.clave.setText("abcd1")
    d.repetir.setText("abcd2")
    d._aceptar()
    assert "no coinciden" in d.aviso.text() and not d.result()
    d.clave.setText("ab")
    d.repetir.setText("ab")
    d._aceptar()
    assert "4 caracteres" in d.aviso.text()


def test_botones_de_qt_en_espanol(ventana):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from pdfcasero.__main__ import traducir

    traducir(QApplication.instance())
    caja = QMessageBox(QMessageBox.Icon.Question, "¿Guardar?", "Hay cambios",
                       QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
    textos = {caja.button(b).text().replace("&", "") for b in (QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Cancel)}
    assert textos == {"Guardar", "Descartar", "Cancelar"}, textos


def test_modo_oscuro_con_letras_claras(ventana, monkeypatch):
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication

    from pdfcasero import estilo

    guardado = {}
    monkeypatch.setattr(type(ventana.ajustes), "setValue", lambda self, k, v: guardado.__setitem__(k, v))
    monkeypatch.setattr(type(ventana.ajustes), "value", lambda self, k, d=None, **_: guardado.get(k, d))
    app = QApplication.instance()
    ventana.bienvenida.muestras["oscuro"].click()
    hoja = app.styleSheet()
    assert "#1f1f23" in hoja and "QWidget { color: #ececf0; }" in hoja  # fondo oscuro, letras claras
    assert app.palette().color(QPalette.ColorRole.Window).lightness() < 80
    assert app.palette().color(QPalette.ColorRole.WindowText).lightness() > 200
    assert ventana.bienvenida.muestras_barra["oscuro"].isChecked()
    # Barra clara con fondo oscuro: las letras de la barra se oscurecen para leerse
    ventana.bienvenida.muestras_barra["rosa"].click()
    assert "QToolBar QToolButton { color: #2b2b2e; }" in app.styleSheet()
    # Volver al gris lo deja todo claro
    ventana.bienvenida.muestras["gris"].click()
    ventana.bienvenida.muestras_barra["gris"].click()
    assert app.palette().color(QPalette.ColorRole.Window).lightness() > 200
    assert app.styleSheet() == estilo.hoja_estilo("gris", "gris")


def test_teclas_zoom_y_nuevo(ventana, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    ventana.abrir(pdf(tmp_path, "teclas", 4))
    app = QApplication.instance()
    app.processEvents()
    assert round(ventana.visor.zoom, 2) == 1.06 and not ventana.visor.ajustar_ancho
    assert ventana.etiqueta_zoom.text() == "106 %"
    # Flechas y espacio pasan de página
    for tecla in ("Right", "Space", "Left", "Shift+Space"):
        assert QKeySequence(tecla) in (ventana.acc_siguiente.shortcuts() + ventana.acc_anterior.shortcuts())
    ventana.visor.setFocus()
    QTest.keyClick(ventana.visor, Qt.Key.Key_Right)
    QTest.keyClick(ventana.visor, Qt.Key.Key_Space)
    app.processEvents()
    assert ventana.visor.pagina_actual == 2
    QTest.keyClick(ventana.visor, Qt.Key.Key_Left)
    app.processEvents()
    assert ventana.visor.pagina_actual == 1
    # En el buscador, el espacio escribe
    ventana.campo_buscar.setFocus()
    QTest.keyClicks(ventana.campo_buscar, "a b")
    QTest.keyClick(ventana.campo_buscar, Qt.Key.Key_Left)
    app.processEvents()
    assert ventana.campo_buscar.text() == "a b" and ventana.visor.pagina_actual == 1
    # Nuevo: PDF en blanco A4, sin guardar, en su pestaña
    monkeypatch.setattr(type(ventana.ajustes), "value", lambda self, k, d=None, **_: str(tmp_path) if k == "ultima_carpeta" else d)
    ventana.nuevo_documento()
    assert ventana.doc.num_paginas == 1 and ventana.doc.nuevo and ventana.doc.modificado
    assert ventana.doc.tamano_pagina(0) == (595, 842)
    assert ventana.doc.ruta == tmp_path / "Documento nuevo.pdf"
    assert len(ventana.abiertos) == 2
    ventana.nuevo_documento()
    assert ventana.doc.ruta.name == "Documento nuevo 2.pdf"
