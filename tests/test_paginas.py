import pymupdf
import pytest

from pdfcasero.documento import Documento


def textos(d):
    return [d._doc[i].get_text().strip() for i in range(d.num_paginas)]


@pytest.fixture
def pdf4(tmp_path):
    ruta = tmp_path / "cuatro.pdf"
    doc = pymupdf.open()
    for i in range(1, 5):
        doc.new_page(width=500, height=700).insert_text((50, 50), f"Página {i}")
    doc.save(ruta)
    return ruta


def test_insertar_en_blanco_en_medio(pdf4):
    d = Documento(pdf4)
    assert d.insertar_en_blanco(2) == 2
    assert textos(d) == ["Página 1", "Página 2", "", "Página 3", "Página 4"]
    assert d.tamano_pagina(2) == (500, 700)  # mismo tamaño que la vecina
    assert d.modificado and d.deshacer()
    assert d.num_paginas == 4


def test_mover_paginas(pdf4):
    d = Documento(pdf4)
    assert d.mover_pagina(0, 3) == 2  # la primera, delante de la cuarta
    assert textos(d) == ["Página 2", "Página 3", "Página 1", "Página 4"]
    assert d.mover_pagina(3, 0) == 0  # la última, al principio
    assert textos(d) == ["Página 4", "Página 2", "Página 3", "Página 1"]
    assert d.mover_pagina(1, 4) == 3  # al final
    assert textos(d) == ["Página 4", "Página 3", "Página 1", "Página 2"]
    assert d.mover_pagina(2, 2) == 2 and d.mover_pagina(2, 3) == 2  # sin cambios


def test_borrar_duplicar_girar(pdf4):
    d = Documento(pdf4)
    d.borrar_paginas([1, 3])
    assert textos(d) == ["Página 1", "Página 3"]
    with pytest.raises(ValueError):
        d.borrar_paginas([0, 1])  # no se puede dejar el PDF sin páginas
    assert d.duplicar_pagina(0) == 1
    assert textos(d) == ["Página 1", "Página 1", "Página 3"]
    d.girar_pagina(2)
    assert d._doc[2].rotation == 90
    d.girar_pagina(2, -90)
    assert d._doc[2].rotation == 0


def test_insertar_otro_pdf_y_una_imagen(pdf4, tmp_path):
    anexo = tmp_path / "anexo.pdf"
    otro = pymupdf.open()
    for t in ("Anexo A", "Anexo B"):
        otro.new_page().insert_text((50, 50), t)
    otro.save(anexo)
    imagen = tmp_path / "foto.png"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 200), False)
    pix.set_rect(pix.irect, (200, 30, 30))
    pix.save(imagen)

    d = Documento(pdf4)
    assert d.insertar_archivo(1, anexo) == 2
    assert textos(d)[:4] == ["Página 1", "Anexo A", "Anexo B", "Página 2"]
    assert d.insertar_archivo(d.num_paginas, imagen) == 1
    ultima = d._doc[d.num_paginas - 1]
    assert ultima.get_images() and ultima.rect.width > ultima.rect.height  # foto apaisada, página apaisada


def test_guardar_tras_reordenar(pdf4, tmp_path):
    d = Documento(pdf4)
    d.mover_pagina(3, 0)
    d.insertar_en_blanco(1)
    destino = d.guardar(tmp_path / "ordenado.pdf")
    assert textos(Documento(destino)) == ["Página 4", "", "Página 1", "Página 2", "Página 3"]
