import pymupdf
import pytest

from pdfcasero.dibujo import TIPOS, Dibujo
from pdfcasero.documento import Documento


@pytest.fixture
def pdf_vacio(tmp_path):
    ruta = tmp_path / "plano.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 60), "Plano de la casa")
    doc.save(ruta)
    return ruta


def ejemplo(tipo):
    d = Dibujo(tipo, (100, 100), (200, 160), texto="Cocina" if tipo in ("globo", "texto") else "")
    if tipo == "lapiz":
        d.trazos = [[(100, 100), (150, 130), (200, 100)]]
    return d


@pytest.mark.parametrize("tipo", TIPOS)
def test_crear_cada_tipo_y_sobrevive_al_guardar(pdf_vacio, tmp_path, tipo):
    d = Documento(pdf_vacio)
    d.anadir_dibujo(0, ejemplo(tipo))
    destino = d.guardar(tmp_path / "con_dibujo.pdf")
    otra = Documento(destino)
    dibujos = otra.dibujos(0)
    assert [x[1].tipo for x in dibujos] == [tipo]
    assert dibujos[0][1] == ejemplo(tipo)  # la receta se conserva tal cual


def test_seleccionar_mover_y_cambiar_color(pdf_vacio):
    d = Documento(pdf_vacio)
    d.anadir_dibujo(0, Dibujo("flecha", (100, 100), (300, 100)))
    d.anadir_dibujo(0, Dibujo("rect", (100, 200), (300, 300)))
    assert d.dibujo_en(0, 200, 101)[1].tipo == "flecha"
    assert d.dibujo_en(0, 200, 201)[1].tipo == "rect"  # borde del rectángulo
    assert d.dibujo_en(0, 200, 250) is None  # dentro de un rectángulo sin relleno no se selecciona
    xref, flecha = d.dibujo_en(0, 200, 101)
    d.cambiar_dibujo(0, xref, flecha.movido(0, 400))
    assert d.dibujo_en(0, 200, 101) is None
    xref, flecha = d.dibujo_en(0, 200, 501)
    assert flecha.a == (100, 500)
    from dataclasses import replace

    d.cambiar_dibujo(0, xref, replace(flecha, color=(0, 0, 1), grosor=5))
    assert d.dibujo_en(0, 200, 501)[1].color == (0, 0, 1)
    assert len(d.dibujos(0)) == 2


def test_estirar_por_las_asas():
    caja = Dibujo("rect", (100, 100), (200, 200))
    assert caja.con_asa(1, (250, 300)).rect() == pymupdf.Rect(100, 100, 250, 300)
    linea = Dibujo("linea", (0, 0), (10, 10))
    assert linea.con_asa(0, (5, 0)).a == (5, 0)
    globo = Dibujo("globo", (50, 50), (100, 0))
    assert globo.con_asa(0, (10, 10)).a == (10, 10)


def test_borrar_y_deshacer(pdf_vacio):
    d = Documento(pdf_vacio)
    xref = d.anadir_dibujo(0, Dibujo("elipse", (100, 100), (200, 200), relleno=True))
    assert d.dibujo_en(0, 150, 150)  # con relleno se selecciona por dentro
    d.borrar_dibujo(0, xref)
    assert d.dibujos(0) == []
    d.deshacer()
    assert len(d.dibujos(0)) == 1


def test_anotaciones_ajenas_no_molestan(pdf_vacio):
    d = Documento(pdf_vacio)
    d._doc[0].add_highlight_annot(pymupdf.Rect(72, 48, 200, 64))
    d.anadir_dibujo(0, Dibujo("linea", (0, 0), (50, 50)))
    assert [x[1].tipo for x in d.dibujos(0)] == ["linea"]
