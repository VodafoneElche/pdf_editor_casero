import pymupdf
import pytest

from pdfcasero.documento import ContrasenaNecesaria, Documento


@pytest.fixture
def pdf_ejemplo(tmp_path):
    ruta = tmp_path / "ejemplo.pdf"
    doc = pymupdf.open()
    for n in range(3):
        p = doc.new_page()
        p.insert_text((72, 72), f"Página {n + 1}: factura de la luz")
        if n == 2:
            p.insert_text((72, 120), "Hello world, factura en inglés")
    doc.new_page()  # página en blanco, como si fuera escaneada
    doc.save(ruta)
    return ruta


def test_abrir_y_paginas(pdf_ejemplo):
    d = Documento(pdf_ejemplo)
    assert d.num_paginas == 4
    assert d.titulo == "ejemplo.pdf"
    assert d.tamano_pagina(0) == pytest.approx((595, 842), abs=1)


def test_renderizar(pdf_ejemplo):
    d = Documento(pdf_ejemplo)
    datos, an, al, paso = d.renderizar(0, 1.0)
    assert (an, al) == (595, 842)
    assert len(datos) == paso * al


def test_buscar_sin_mayusculas(pdf_ejemplo):
    d = Documento(pdf_ejemplo)
    res = d.buscar("FACTURA")
    assert [r.pagina for r in res] == [0, 1, 2, 2]
    assert d.buscar("   ") == []
    assert d.buscar("no existe") == []


def test_detecta_pagina_sin_texto(pdf_ejemplo):
    d = Documento(pdf_ejemplo)
    assert d.tiene_texto(0)
    assert not d.tiene_texto(3)


def test_contrasena(tmp_path):
    ruta = tmp_path / "secreto.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secreto")
    doc.save(ruta, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="1234")
    with pytest.raises(ContrasenaNecesaria):
        Documento(ruta)
    with pytest.raises(ContrasenaNecesaria):
        Documento(ruta, "mal")
    assert Documento(ruta, "1234").num_paginas == 1
