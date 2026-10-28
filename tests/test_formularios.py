import pymupdf
import pytest

from pdfcasero.documento import Documento


@pytest.fixture
def pdf_ficha(tmp_path):
    ruta = tmp_path / "ficha.pdf"
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 90), "Nombre:")
    p.insert_text((72, 130), "Acepto las normas")
    doc.save(ruta)
    return ruta


def test_crear_rellenar_y_abrir_en_otro_lector(pdf_ficha, tmp_path):
    d = Documento(pdf_ficha)
    x_nombre = d.crear_campo(0, "texto", (130, 76, 400, 96))
    x_notas = d.crear_campo(0, "multilinea", (72, 200, 500, 300))
    x_casilla = d.crear_campo(0, "casilla", (250, 118, 0, 0))
    assert [c.nombre for c in d.campos(0)] == ["Texto 1", "Texto largo 1", "Casilla 1"]
    d.renombrar_campo(0, x_nombre, "Nombre")
    destino = d.guardar(tmp_path / "formulario.pdf")

    # Quien lo recibe lo rellena (aquí con PyMuPDF directamente, como haría otro lector)
    recibido = pymupdf.open(destino)
    assert recibido.is_form_pdf == 3
    for w in recibido[0].widgets():
        if w.field_name == "Nombre":
            w.field_value = "José Pérez"
        elif w.field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
            w.field_value = w.on_state()
        else:
            w.field_value = "Alergia a los frutos secos"
        w.update()
    recibido.save(tmp_path / "relleno.pdf")

    leido = Documento(tmp_path / "relleno.pdf")
    valores = {c.nombre: c.valor for c in leido.campos(0)}
    assert valores == {"Nombre": "José Pérez", "Texto largo 1": "Alergia a los frutos secos", "Casilla 1": True}
    assert x_notas and x_casilla


def test_rellenar_mover_borrar_y_deshacer(pdf_ficha):
    d = Documento(pdf_ficha)
    xref = d.crear_campo(0, "texto", (130, 76, 400, 96))
    casilla = d.crear_campo(0, "casilla", (250, 118, 0, 0))
    d.rellenar_campo(0, xref, "Ana")
    d.rellenar_campo(0, casilla, True)
    assert d.campo_en(0, 200, 85).valor == "Ana"
    assert d.campo_en(0, 255, 125).marcado
    d.rellenar_campo(0, casilla, False)
    assert not d.campo_en(0, 255, 125).marcado
    d.mover_campo(0, xref, (130, 400, 400, 420))
    assert d.campo_en(0, 200, 85) is None and d.campo_en(0, 200, 410).valor == "Ana"
    d.borrar_campo(0, xref)
    assert [c.tipo for c in d.campos(0)] == ["casilla"]
    d.deshacer()
    assert len(d.campos(0)) == 2


def test_nombres_unicos(pdf_ficha):
    d = Documento(pdf_ficha)
    a = d.crear_campo(0, "texto", (100, 100, 200, 120))
    d.crear_campo(0, "texto", (100, 140, 200, 160))
    with pytest.raises(ValueError):
        d.renombrar_campo(0, a, "Texto 2")
    with pytest.raises(ValueError):
        d.renombrar_campo(0, a, "  ")
    d.renombrar_campo(0, a, "Teléfono")
    assert d.crear_campo(0, "texto", (100, 180, 200, 200))
    assert [c.nombre for c in d.campos(0)] == ["Teléfono", "Texto 2", "Texto 1"]
