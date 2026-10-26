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


def test_guardar_como_y_guardar(pdf_ejemplo, tmp_path):
    d = Documento(pdf_ejemplo)
    copia = d.guardar(tmp_path / "copia.pdf")
    assert copia.exists() and d.ruta == copia and not d.modificado
    assert Documento(copia).num_paginas == 4
    # Guardar encima del mismo archivo y seguir usándolo
    d.modificado = True
    d.guardar()
    assert not d.modificado
    assert d.buscar("factura")
    assert [p.name for p in tmp_path.glob("tmp*.pdf")] == []


def test_guardar_pdf_con_contrasena(tmp_path):
    ruta = tmp_path / "secreto.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secreto")
    doc.save(ruta, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="1234")
    d = Documento(ruta, "1234")
    d.guardar()
    assert d.num_paginas == 1 and d.buscar("secreto")


@pytest.fixture
def pdf_texto(tmp_path):
    ruta = tmp_path / "texto.pdf"
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 72), "Querida familia", fontsize=14, color=(0.8, 0, 0), fontname="tiro")
    p.insert_text((72, 100), "Hoy cenamos paella a las nueve", fontsize=12)
    p.draw_rect(pymupdf.Rect(60, 50, 400, 120), color=(0, 0, 1))
    doc.save(ruta)
    return ruta


def test_cambiar_linea_conserva_estilo_y_lo_demas(pdf_texto):
    d = Documento(pdf_texto)
    linea = d.linea_en(0, 100, 68)
    assert linea.texto == "Querida familia"
    d.cambiar_linea(0, linea, "Queridos abuelos")
    assert d.modificado
    assert d.buscar("Queridos abuelos") and not d.buscar("Querida familia")
    assert d.buscar("paella")  # la otra línea sigue igual
    nueva = d.linea_en(0, 100, 68)
    assert nueva.fuente == "tiro" and nueva.color == (0.8, 0, 0) and round(nueva.tamano) == 14
    assert len(d._doc[0].get_drawings()) == 1  # el recuadro no se toca


def test_borrar_linea_y_palabras(pdf_texto):
    d = Documento(pdf_texto)
    d.cambiar_linea(0, d.linea_en(0, 100, 68), "")
    assert not d.buscar("Querida")
    palabras = [w[4] for w in d.palabras(0)]
    i = palabras.index("paella")
    d.borrar_palabras(0, i, i + 1)  # "paella a"
    assert [w[4] for w in d.palabras(0)] == ["Hoy", "cenamos", "las", "nueve"]


def test_escribir_deshacer_rehacer(pdf_texto):
    d = Documento(pdf_texto)
    assert not d.puede_deshacer
    d.escribir(0, 72, 200, "Nota añadida: llevar pan")
    assert d.buscar("llevar pan")
    assert d.deshacer() and not d.buscar("llevar pan")
    assert d.puede_rehacer
    assert d.rehacer() and d.buscar("llevar pan")
    d.escribir(0, 72, 250, "otra")
    assert not d.puede_rehacer  # un cambio nuevo borra lo que se podía rehacer
