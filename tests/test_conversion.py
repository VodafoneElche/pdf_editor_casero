import pymupdf

from pdfcasero import conversion


def test_pdf_a_word_y_vuelta(tmp_path):
    pdf = tmp_path / "carta.pdf"
    doc = pymupdf.open()
    pagina = doc.new_page()
    pagina.insert_text((72, 80), "Carta para la familia", fontsize=18)
    pagina.insert_htmlbox(pymupdf.Rect(72, 110, 400, 140), "<p>Precio: 25 € al mes</p>")
    doc.save(pdf)

    docx = tmp_path / "carta.docx"
    conversion.pdf_a_word(str(pdf), str(docx))
    assert docx.stat().st_size > 1000

    vuelta = tmp_path / "vuelta.pdf"
    metodo = conversion.word_a_pdf(str(docx), str(vuelta))
    assert metodo in ("Word", "mammoth")
    texto = pymupdf.open(vuelta)[0].get_text()
    assert "Carta para la familia" in texto and "25 €" in texto


def test_exportacion_en_proceso_aparte(tmp_path):
    import time

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 80), "Hola", fontsize=12)
    destino = tmp_path / "hola.docx"
    trabajo = conversion.ExportacionWord(doc.tobytes(), str(destino))
    limite = time.time() + 120
    resultado = None
    while resultado is None and time.time() < limite:
        time.sleep(0.2)
        resultado = trabajo.resultado()
    assert resultado == ("ok", str(destino)), resultado
    assert destino.stat().st_size > 1000
