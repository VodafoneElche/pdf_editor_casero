"""Desplazamiento suave con rueda y touchpad."""

import os

import pymupdf
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def visor(tmp_path):
    from PySide6.QtWidgets import QApplication

    from pdfcasero.documento import Documento
    from pdfcasero.visor import VisorPDF

    QApplication.instance() or QApplication([])
    ruta = tmp_path / "largo.pdf"
    doc = pymupdf.open()
    for i in range(6):
        doc.new_page().insert_text((72, 100), f"Pagina {i + 1}", fontsize=14)
    doc.save(ruta)
    v = VisorPDF()
    v.resize(700, 500)
    v.show()
    v.cargar(Documento(ruta))
    from PySide6.QtTest import QTest

    QTest.qWait(200)  # deja que termine el ajuste al ancho tras abrir
    yield v
    v.close()


def rueda(visor, angulo_y=0, pixeles_y=0, angulo_x=0):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    ev = QWheelEvent(
        QPointF(100, 100), QPointF(100, 100), QPoint(0, pixeles_y), QPoint(angulo_x, angulo_y),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False,
    )
    visor.wheelEvent(ev)


def esperar_fin(visor):
    from PySide6.QtTest import QTest

    valores = []
    for _ in range(200):
        QTest.qWait(16)
        valores.append(visor.verticalScrollBar().value())
        if not visor._suave_v.activo:
            break
    return valores


def test_una_muesca_de_rueda_se_desliza_en_varios_pasos(visor):
    rueda(visor, angulo_y=-120)
    valores = esperar_fin(visor)
    esperado = round(120 / 120 * 3 * 36)  # 3 líneas por muesca
    assert valores[-1] == esperado
    # No llega de un salto: pasa por posiciones intermedias
    assert len(set(valores)) >= 4


def test_touchpad_mueve_poco_a_poco_sin_perder_movimientos_pequenos(visor):
    # Un touchpad de Windows manda muchos giros pequeños (p. ej. 8 de 120)
    for _ in range(30):
        rueda(visor, angulo_y=-8)
    valores = esperar_fin(visor)
    assert valores[-1] == round(30 * 8 / 120 * 3 * 36)


def test_pixeles_exactos_se_usan_tal_cual(visor):
    rueda(visor, angulo_y=-120, pixeles_y=-50)
    assert esperar_fin(visor)[-1] == 50


def test_no_se_pasa_del_principio(visor):
    rueda(visor, angulo_y=600)
    assert esperar_fin(visor)[-1] == 0


def test_ir_a_pagina_corta_la_animacion(visor):
    rueda(visor, angulo_y=-1200)
    visor.ir_a_pagina(4)
    destino = visor.verticalScrollBar().value()
    esperar_fin(visor)
    assert visor.verticalScrollBar().value() == destino
    assert visor.pagina_actual == 4


def test_al_pararse_prepara_la_pagina_siguiente(visor):
    from PySide6.QtTest import QTest

    visor._cache.clear()
    visor.ir_a_pagina(2)
    QTest.qWait(250)
    paginas = {clave[0] for clave in visor._cache}
    assert {1, 3} <= paginas
