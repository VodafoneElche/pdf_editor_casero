import pymupdf
import pytest

from pdfcasero import edicion, ocr
from pdfcasero.documento import Documento

TESSDATA = ocr.buscar_tessdata()
requiere_idiomas = pytest.mark.skipif(TESSDATA is None, reason="faltan los idiomas del OCR")

TEXTO = (
    "Factura de la luz\n\n"
    "Estimado cliente: el importe de su factura de octubre es de 54,30 euros.\n\n"
    "The quick brown fox jumps over the lazy dog."
)


@pytest.fixture
def pdf_escaneado(tmp_path):
    """Un PDF que solo tiene una imagen, como si saliera del escáner."""
    original = pymupdf.open()
    p = original.new_page()
    p.insert_textbox(pymupdf.Rect(60, 60, 540, 400), TEXTO, fontsize=13)
    imagen = p.get_pixmap(dpi=200)
    escaneado = pymupdf.open()
    pagina = escaneado.new_page(width=p.rect.width, height=p.rect.height)
    pagina.insert_image(pagina.rect, pixmap=imagen)
    escaneado.new_page().insert_text((72, 72), "Esta página ya tiene texto")
    ruta = tmp_path / "escaneado.pdf"
    escaneado.save(ruta)
    return ruta


def test_capa_invisible_en_su_sitio():
    doc = pymupdf.open()
    for giro in (0, 90, 180, 270):
        pagina = doc.new_page()
        pagina.set_rotation(giro)
        ocr.insertar_capa_texto(pagina, [(100, 100, 140, 112, "Hola"), (150, 100, 200, 112, "mundo")])
        palabras = pagina.get_text("words")
        assert [w[4] for w in palabras] == ["Hola", "mundo"]
        assert palabras[0][0] == pytest.approx(100, abs=2)
        assert 90 < palabras[0][1] < 112 < palabras[0][3] < 118


def test_buscar_tessdata_con_variable(tmp_path, monkeypatch):
    for idioma in ocr.IDIOMAS:
        (tmp_path / f"{idioma}.traineddata").write_bytes(b"x")
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_path))
    assert ocr.buscar_tessdata() == tmp_path


@requiere_idiomas
def test_hacer_editable(pdf_escaneado, tmp_path):
    d = Documento(pdf_escaneado)
    assert d.paginas_sin_texto() == [0]
    assert d.buscar("factura") == []

    copia = pymupdf.open(stream=d.copia_en_memoria(), filetype="pdf")
    palabras = ocr.reconocer_pagina(copia[0], TESSDATA)
    d.aplicar_ocr(0, palabras)

    assert d.modificado
    assert d.paginas_sin_texto() == []
    assert len(d.buscar("factura")) == 2
    assert d.buscar("54,30")
    assert d.buscar("lazy dog")
    # Se guarda y el texto sigue ahí al volver a abrir
    destino = d.guardar(tmp_path / "editable.pdf")
    assert len(Documento(destino).buscar("octubre")) == 1


def test_texto_entre_respeta_lineas(tmp_path):
    ruta = tmp_path / "lineas.pdf"
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 72), "Primera línea aquí")
    p.insert_text((72, 100), "Segunda línea")
    doc.save(ruta)
    d = Documento(ruta)
    assert d.texto_entre(0, 0, 4) == "Primera línea aquí\nSegunda línea"
    assert d.texto_entre(0, 1, 3) == "línea aquí\nSegunda"


@requiere_idiomas
def test_editar_escaneado_tapa_la_imagen(pdf_escaneado):
    d = Documento(pdf_escaneado)
    copia = pymupdf.open(stream=d.copia_en_memoria(), filetype="pdf")
    d.aplicar_ocr(0, ocr.reconocer_pagina(copia[0], TESSDATA))
    linea = next(l for l in edicion.lineas(d._doc[0]) if "Estimado" in l.texto)
    assert linea.invisible
    d.cambiar_linea(0, linea, "Estimada familia: texto cambiado")
    assert d.buscar("texto cambiado")
    # Al volver a pasar el OCR sobre cómo se ve ahora la página, el texto viejo ya no está
    visto = pymupdf.open(stream=d.copia_en_memoria(), filetype="pdf")[0]
    pix = visto.get_pixmap(dpi=200)
    solo_imagen = pymupdf.open()
    pagina = solo_imagen.new_page(width=visto.rect.width, height=visto.rect.height)
    pagina.insert_image(pagina.rect, pixmap=pix)
    texto = " ".join(w[4] for w in ocr.reconocer_pagina(pagina, TESSDATA))
    assert "cambiado" in texto
    assert "informamos" not in texto
